import cv2
import mediapipe as mp
import pyautogui
import numpy as np
import threading
import time
import math
import tkinter as tk
from PIL import Image, ImageTk
import queue
import sys
import pyttsx3

# Disable pyautogui safety stops to allow full-screen control smoothly
pyautogui.PAUSE = 0
pyautogui.FAILSAFE = False

class TrackedHand:
    def __init__(self, hand_id, centroid):
        self.id = hand_id
        self.centroid = centroid
        self.fist_start = None
        self.is_selected = False
        self.last_seen = time.time()
        self.landmarks = None

class HandGestureController:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Hand Gesture Cursor Control")
        
        # UI & Window setup - clean & dark theme
        window_w, window_h = 800, 680
        self.screen_w, self.screen_h = pyautogui.size()
        pos_x = int((self.screen_w / 2) - (window_w / 2))
        pos_y = int((self.screen_h / 2) - (window_h / 2))
        self.root.geometry(f"{window_w}x{window_h}+{pos_x}+{pos_y}")
        self.root.configure(bg="#121212")
        self.root.resizable(False, False)
        
        # Header setup
        header_frame = tk.Frame(self.root, bg="#121212")
        header_frame.pack(fill=tk.X, pady=(15, 5))
        title_label = tk.Label(header_frame, text="Real-Time Gesture Cursor", font=("Segoe UI", 20, "bold"), fg="#ffffff", bg="#121212")
        title_label.pack()
        
        # Video display canvas/label
        self.video_label = tk.Label(self.root, bg="#1a1a1a", relief="flat")
        self.video_label.pack(expand=True, padx=20, pady=10)
        
        # Status footer setup
        self.status_var = tk.StringVar()
        self.status_var.set("Initializing Camera...")
        self.status_label = tk.Label(self.root, textvariable=self.status_var, font=("Segoe UI", 16, "bold"), fg="#aaaaaa", bg="#121212")
        self.status_label.pack(side=tk.BOTTOM, pady=(0, 20))
        
        self.frame_queue = queue.Queue(maxsize=3)
        self.running = True
        
        # Cursor parameters
        self.alpha = 0.3  # Moving average smoothing factor for cursor
        current_mouse = pyautogui.position()
        self.cursor_x = current_mouse.x
        self.cursor_y = current_mouse.y
        self.box_margin = 120  # Inner invisible box limit mapped to physical screen boundaries
        
        self.current_gesture = None
        self.gesture_start_time = None
        self.action_executed = False
        
        # Audio setup
        self.speech_queue = queue.Queue()
        self.speech_thread = threading.Thread(target=self.speech_worker, daemon=True)
        self.speech_thread.start()
        
        self.said_primary = False
        self.said_secondary = False
        self.arms_crossed_start_time = None
        
        # Start background processing thread
        self.thread = threading.Thread(target=self.process_video, daemon=True)
        self.thread.start()
        
        # Bind exit hooks
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.root.bind('<Escape>', self.on_close)
        
        # Start UI render loop
        self.update_ui()
        
    def on_close(self, event=None):
        self.running = False
        self.root.destroy()
        sys.exit(0)
        
    def speech_worker(self):
        engine = pyttsx3.init()
        engine.setProperty('rate', 160)
        # Try to use a more robotic voice if available
        voices = engine.getProperty('voices')
        for voice in voices:
            if "Zira" in voice.name or "David" in voice.name or "Hazel" in voice.name:
                engine.setProperty('voice', voice.id)
                break
                
        while self.running:
            try:
                msg = self.speech_queue.get(timeout=0.1)
                engine.say(msg)
                engine.runAndWait()
            except queue.Empty:
                pass
                
    def update_ui(self):
        """ Pulls newly processed frames from the queued background thread to update Tkinter. """
        if not self.running:
            return
            
        latest_item = None
        # Drain the queue to keep real-time UI feel mapping and ignoring skipped frames
        while not self.frame_queue.empty():
            try:
                latest_item = self.frame_queue.get_nowait()
            except queue.Empty:
                break
                
        if latest_item is not None:
            frame, status_text = latest_item
            img = Image.fromarray(frame)
            imgtk = ImageTk.PhotoImage(image=img)
            self.video_label.imgtk = imgtk
            self.video_label.configure(image=imgtk)
            
            # Dynamic colors based on status
            color = "#aaaaaa"
            if "Hold fist" in status_text:
                color = "#ffaa00"
            elif "Tracking active" in status_text:
                color = "#00ff00"
            elif "lost!" in status_text:
                color = "#ff5555"
                
            self.status_label.configure(fg=color)
            self.status_var.set(status_text)
            
        # UI Refresh Rate roughly locking 60 FPS update
        self.root.after(16, self.update_ui)

    def process_video(self):
        """ Main cv2/MediaPipe logical thread running continuously for speed. """
        cap = cv2.VideoCapture(0)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        cap.set(cv2.CAP_PROP_FPS, 30)
        
        mp_hands = mp.solutions.hands
        hands = mp_hands.Hands(
            min_detection_confidence=0.7,
            min_tracking_confidence=0.7,
            max_num_hands=2
        )
        mp_draw = mp.solutions.drawing_utils
        
        tracked_hands = {}
        next_hand_id = 1
        
        while self.running:
            success, img = cap.read()
            if not success:
                time.sleep(0.01)
                continue
                
            img = cv2.flip(img, 1) # Mirror logic
            h, w, c = img.shape
            img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            
            results = hands.process(img_rgb)
            status_text = "No hand detected"
            
            matched_ids = set()
            
            if results.multi_hand_landmarks:
                for hand_landmarks in results.multi_hand_landmarks:
                    wrist = hand_landmarks.landmark[0]
                    cx, cy = int(wrist.x * w), int(wrist.y * h)
                    
                    best_id = None
                    best_dist = float('inf')
                    
                    # Proximity match to tracking stable hands
                    for th_id, th in tracked_hands.items():
                        if th_id not in matched_ids:
                            dist = math.hypot(cx - th.centroid[0], cy - th.centroid[1])
                            if dist < 200 and dist < best_dist:
                                best_id = th_id
                                best_dist = dist
                                
                    if best_id is not None:
                        matched_ids.add(best_id)
                        th = tracked_hands[best_id]
                        th.centroid = (cx, cy)
                        th.last_seen = time.time()
                        th.landmarks = hand_landmarks
                    else:
                        new_id = next_hand_id
                        next_hand_id += 1
                        th = TrackedHand(new_id, (cx, cy))
                        th.landmarks = hand_landmarks
                        th.last_seen = time.time()
                        tracked_hands[new_id] = th
                        matched_ids.add(new_id)

            current_time = time.time()
            
            # --- Crossed Arms Heuristic ---
            crossed_arms_eval = False
            if results.multi_hand_landmarks and len(results.multi_hand_landmarks) == 2:
                if results.multi_handedness and len(results.multi_handedness) == 2:
                    hand1_label = results.multi_handedness[0].classification[0].label
                    hand2_label = results.multi_handedness[1].classification[0].label
                    
                    hx1 = results.multi_hand_landmarks[0].landmark[0].x
                    hx2 = results.multi_hand_landmarks[1].landmark[0].x
                    
                    # More forgiving detection distance for overlaps
                    if hand1_label == 'Left' and hand2_label == 'Right':
                        if hx1 > hx2 - 0.1: 
                            crossed_arms_eval = True
                    elif hand1_label == 'Right' and hand2_label == 'Left':
                        if hx2 > hx1 - 0.1: 
                            crossed_arms_eval = True

            # Tolerance check to prevent stutter drops
            if crossed_arms_eval:
                self.last_crossed_time = current_time
                
            crossed_arms_now = False
            if hasattr(self, 'last_crossed_time') and (current_time - self.last_crossed_time) < 1.0:
                crossed_arms_now = True

            if crossed_arms_now:
                if self.arms_crossed_start_time is None:
                    self.arms_crossed_start_time = time.time()
                else:
                    elapsed = time.time() - self.arms_crossed_start_time
                    cv2.putText(img_rgb, f"SYSTEM SHUTDOWN IN: {max(0.0, 3.0 - elapsed):.1f}S", (w//2 - 200, h - 50), 
                                cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 255), 3)
                                
                    if elapsed >= 3.0:
                        any_selected = False
                        for th in tracked_hands.values():
                            if th.is_selected:
                                any_selected = True
                            th.is_selected = False
                            th.fist_start = None
                            
                        if any_selected:
                            self.speech_queue.put("Steering system offline")
                            self.said_primary = False
                            self.said_secondary = False
                            
                        self.arms_crossed_start_time = None
                        self.last_crossed_time = 0  # reset tolerance correctly
                        status_text = "Steering system offline"
            else:
                self.arms_crossed_start_time = None

            # Cull tracking for hands that are missing for more than 3 sec
            for th_id in list(tracked_hands.keys()):
                if th_id not in matched_ids:
                    time_lost = current_time - tracked_hands[th_id].last_seen
                    if time_lost > 3.0:
                        del tracked_hands[th_id]
                        
            # Execute gestures & logic
            drawing_elements = []  
            
            for th_id in matched_ids:
                th = tracked_hands[th_id]
                landmarks = th.landmarks
                
                is_fist_now = self.check_fist(landmarks)
                if is_fist_now:
                    if th.fist_start is None:
                        th.fist_start = time.time()
                else:
                    th.fist_start = None
                    
                loading_progress = 0
                if th.fist_start is not None:
                    elapsed = time.time() - th.fist_start
                    loading_progress = min(1.0, elapsed / 5.0)
                    
                    # Threshold reached => Elect this hand
                    if elapsed >= 5.0 and not th.is_selected:
                        for oth in tracked_hands.values():
                            oth.is_selected = False
                        th.is_selected = True
                        th.fist_start = None
                        if not self.said_primary:
                            self.speech_queue.put("Primary steering system initiated")
                            self.said_primary = True
                
                # Setup render bounding
                x_list = [int(lm.x * w) for lm in landmarks.landmark]
                y_list = [int(lm.y * h) for lm in landmarks.landmark]
                xmin, xmax = min(x_list), max(x_list)
                ymin, ymax = min(y_list), max(y_list)
                
                pad = 20
                box_pts = (xmin - pad, ymin - pad, xmax + pad, ymax + pad)
                drawing_elements.append((th, box_pts, loading_progress))
                
                # Render underlying map
                mp_draw.draw_landmarks(img_rgb, landmarks, mp_hands.HAND_CONNECTIONS)
                
            # Perform Drawing & Mouse UI logic Overlays
            is_any_hand_selected = any(th.is_selected for th in tracked_hands.values())
            if not is_any_hand_selected:
                self.said_primary = False
                self.said_secondary = False
            
            selected_th = next((th for th in tracked_hands.values() if th.is_selected), None)
            if selected_th and selected_th.id not in matched_ids:
                time_lost = time.time() - selected_th.last_seen
                if time_lost < 3.0:
                    status_text = f"Controlling hand lost! Waiting {3.0 - time_lost:.1f}s"
                    
            for th, (b_xmin, b_ymin, b_xmax, b_ymax), loading_progress in drawing_elements:
                cx, cy = th.centroid
                
                if th.is_selected:
                    hand_color = (0, 255, 0) # Green aura bounds
                    border_thick = 4
                    status_text = "Tracking active"
                    b_xmin, b_ymin = max(0, b_xmin), max(0, b_ymin)
                    
                    # Mouse coordinate linear extrapolation and limiting
                    index_tip = th.landmarks.landmark[8]
                    ix, iy = int(index_tip.x * w), int(index_tip.y * h)
                    
                    screen_x = np.interp(ix, [self.box_margin, w - self.box_margin], [self.screen_w, 0])
                    screen_y = np.interp(iy, [self.box_margin, h - self.box_margin], [0, self.screen_h])
                    
                    # Low Pass Exponential Smoothing Formula to avoid jitter
                    self.cursor_x = self.alpha * screen_x + (1 - self.alpha) * self.cursor_x
                    self.cursor_y = self.alpha * screen_y + (1 - self.alpha) * self.cursor_y
                    
                    try:
                        pyautogui.moveTo(int(self.cursor_x), int(self.cursor_y))
                    except pyautogui.FailSafeException:
                        pass
                else:
                    hand_color = (255, 50, 50) # Inactive tracking visual
                    border_thick = 2
                    
                    if not is_any_hand_selected and th.fist_start is None:
                        status_text = "Hand detected. Hold fist to select."
                        
                    cv2.rectangle(img_rgb, (b_xmin, b_ymin), (b_xmax, b_ymax), hand_color, border_thick)
                    cv2.putText(img_rgb, f"ID: {th.id}", (b_xmin, max(20, b_ymin - 10)), 
                                cv2.FONT_HERSHEY_SIMPLEX, 0.6, hand_color, 2)
                                
                    if th.fist_start is not None:
                        # Draw circle countdown
                        center = (cx, cy)
                        radius = 50
                        angle = int(360 * loading_progress)
                        cv2.ellipse(img_rgb, center, (radius, radius), -90, 0, angle, (0, 255, 255), 6)
                        status_text = f"Hold fist to select... {int(loading_progress*100)}%"
                        
            # Draw movement bounds mapping limits visualization
            cv2.rectangle(img_rgb, (self.box_margin, self.box_margin), 
                          (w - self.box_margin, h - self.box_margin), 
                          (255, 255, 255), 1, lineType=cv2.LINE_AA)
                          
            # --- Click gestures check ---
            if is_any_hand_selected:
                other_hand_fingers = None
                other_hand_present = False
                for th_id in matched_ids:
                    th = tracked_hands[th_id]
                    if not th.is_selected:
                        other_hand_fingers = self.check_fingers(th.landmarks)
                        other_hand_present = True
                        break
                        
                if other_hand_present:
                    cv2.putText(img_rgb, "SECONDARY STEERING SYSTEM INITIALIZED", (20, 40), 
                                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
                    if not self.said_secondary:
                        self.speech_queue.put("Secondary system initiated")
                        self.said_secondary = True
                else:
                    self.said_secondary = False
                        
                if other_hand_fingers is not None:
                    index_ext, middle_ext, ring_ext, pinky_ext = other_hand_fingers
                    
                    gesture = None
                    if index_ext and not middle_ext and not ring_ext and not pinky_ext:
                        gesture = 'left'
                    elif index_ext and middle_ext and not ring_ext and not pinky_ext:
                        gesture = 'right'
                        
                    if gesture is not None:
                        if self.current_gesture != gesture:
                            self.current_gesture = gesture
                            self.gesture_start_time = time.time()
                            self.action_executed = False
                        else:
                            elapsed = time.time() - self.gesture_start_time
                            if elapsed >= 1.0 and not self.action_executed:
                                try:
                                    pyautogui.click(button=gesture)
                                    self.action_executed = True
                                except pyautogui.FailSafeException:
                                    pass
                            elif not self.action_executed:
                                # Show loading for click
                                load_pct = int(min(1.0, elapsed / 1.0) * 100)
                                cv2.putText(img_rgb, f"{gesture.upper()} CLICK LOADING: {load_pct}%", (20, 70), 
                                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 165, 255), 2)
                    else:
                        self.current_gesture = None
                        self.gesture_start_time = None
                        self.action_executed = False
                else:
                    self.current_gesture = None
                    self.gesture_start_time = None
                    self.action_executed = False
                            
            # Deliver to UI thread
            if not self.frame_queue.full():
                self.frame_queue.put((img_rgb, status_text))
                
        cap.release()

    def check_fist(self, landmarks):
        """ Evaluates logic verifying if 4 primary fingers are internally folded inside the palm towards the wrist """
        fingers_tips = [8, 12, 16, 20]
        fingers_mcp = [5, 9, 13, 17]
        wrist = landmarks.landmark[0]
        
        def dist(p1, p2):
            return math.hypot(p1.x - p2.x, p1.y - p2.y)
            
        for tip_idx, mcp_idx in zip(fingers_tips, fingers_mcp):
            tip = landmarks.landmark[tip_idx]
            mcp = landmarks.landmark[mcp_idx]
            # When tips wrap lower than their knuckle roots, standard physical hand is closed
            if dist(tip, wrist) > dist(mcp, wrist):
                return False
        return True

    def check_fingers(self, landmarks):
        """ Evaluates logic verifying which fingers are extended (index, middle, ring, pinky) """
        fingers_tips = [8, 12, 16, 20]
        fingers_pip = [6, 10, 14, 18]
        wrist = landmarks.landmark[0]
        
        def dist(p1, p2):
            return math.hypot(p1.x - p2.x, p1.y - p2.y)
            
        extended = []
        for tip_idx, pip_idx in zip(fingers_tips, fingers_pip):
            tip = landmarks.landmark[tip_idx]
            pip = landmarks.landmark[pip_idx]
            # If tip is further from wrist than the PIP joint, it's extended
            extended.append(dist(tip, wrist) > dist(pip, wrist))
        return extended

if __name__ == "__main__":
    app = HandGestureController()
    app.root.mainloop()

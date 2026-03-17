# Real-Time Gesture Cursor Control

This is a production-ready desktop application that allows you to control your mouse cursor using hand gestures in real-time. It uses your webcam, OpenCV, and MediaPipe for accurate hand tracking.

## 🎓 About This Project

**This project was realized together with my students at [STEP IT Academy](https://itstep.org/).** It serves as a practical, hands-on demonstration of real-time computer vision, multithreading, and user interface design in Python.

## 🚀 Features

* **Real-time Navigation:** Multithreaded architecture ensures smooth >30 FPS tracking.
* **Smart Hand Tracking:** Tracks multiple hands, assigns IDs, and retains memory of hands even through brief tracking losses.
* **Gesture Locking:** Close your hand into a fist holding it for 5 seconds to lock it as the primary controlling hand.
* **Cursor Control:** Cursor follows your primary hand's index finger, utilizing Exponential Moving Average (EMA) to prevent jitter.
* **Click Actions:** Use your secondary hand to perform mouse clicks without disrupting the primary hand:
  * **Left Click:** Raise 1 finger (Index)
  * **Right Click:** Raise 2 fingers (Index & Middle)
* **Dark Mode UI:** Configured with an overlay mapping box, real-time indicators, and smooth visual feedback.

## ⚙️ Installation

1. Ensure you have Python 3.10+ installed.
2. Clone this repository to your local machine:
   ```bash
   git clone https://github.com/yourusername/gesture-cursor-control.git
   cd gesture-cursor-control
   ```
3. Install the required dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## 🎮 How to Use

Run the main application:
```bash
python main.py
```

1. **Selection:** Show your hand to the camera. Close your fist and hold it for 5 seconds until the loading arc reaches 100%. The tracking box will turn green, indicating the hand is locked and controlling the cursor.
2. **Moving:** Move your locked hand's index finger around the screen.
3. **Clicking:** Raise your other hand into the frame. Extend your index finger for a Left Click, or extend your index and middle fingers for a Right Click.
4. **Exit:** Press the `ESC` key or use the close button on the window to safely stop the tracking threads and terminate the app.

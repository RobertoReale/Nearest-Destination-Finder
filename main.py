from gui.app_window import AppWindow
from utils.logger import setup_logger

if __name__ == "__main__":
    setup_logger().info("Starting Nearest Destination Finder")
    app = AppWindow()
    app.mainloop()

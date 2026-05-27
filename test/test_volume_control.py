import unittest
import time
import os
from pywinauto.application import Application

sample_fest_path = os.path.abspath(r"..\..	est\data\sample.fest")

class VolumeControlTests(unittest.TestCase):
    def __init__(self, *args, **kwargs):
        super(VolumeControlTests, self).__init__(*args, **kwargs)
        self.app = None

    def setUp(self):
        # Change directory to where FestEngine.exe is located
        os.chdir(os.path.join(os.path.split(__file__)[0], "..", "bin", "FestEngine"))
        self.assertTrue(os.path.isfile("FestEngine.exe"), "FestEngine.exe not found. Please build the project.")
        self.assertTrue(os.path.isfile(sample_fest_path), "sample.fest not found. Please ensure test data exists.")

        # Ensure last_fest.txt is clean for a fresh start
        if os.path.isfile("last_fest.txt"):
            os.remove("last_fest.txt")

        self.app = Application().start("FestEngine.exe")
        time.sleep(2)  # Give time for the app to start and initial dialogs to appear

        # Handle "Welcome to Fest Engine" dialog
        try:
            welcome_dialog = self.app.window(title="Welcome to Fest Engine")
            if welcome_dialog.exists():
                welcome_dialog.OK.click()
                time.sleep(1)
        except Exception:
            pass # Dialog might not appear on subsequent runs if last_fest.txt exists

        # Load the sample fest file
        settings = self.app.Settings
        settings['Current Fest:Edit'].set_text(sample_fest_path)
        time.sleep(0.5)
        settings.Load.click()
        time.sleep(2) # Give time for loading and restart prompt

        # Handle "Restart Required" dialog
        try:
            restart_dialog = self.app.window(title="Restart Required")
            if restart_dialog.exists():
                restart_dialog.Button2.click() # Click 'No' to avoid restart, we'll restart manually if needed
                time.sleep(1)
        except Exception:
            pass # Dialog might not appear if config hasn't changed

        # Re-launch if it was restarted or if 'No' was clicked on restart dialog
        if not self.app.is_process_running():
            self.app = Application().start("FestEngine.exe")
            time.sleep(2)
            try:
                welcome_dialog = self.app.window(title="Welcome to Fest Engine")
                if welcome_dialog.exists():
                    welcome_dialog.OK.click()
                    time.sleep(1)
            except Exception:
                pass

        self.main_window = self.app.wxWindowNR
        self.assertTrue(self.main_window.exists(), "Main window did not appear.")
        time.sleep(1)


    def test_independent_volume_control(self):
        # Open Background Music Window
        self.main_window.menu_select("Background Music -> Open Window")
        time.sleep(1)
        bg_music_window = self.app.window(title="Background Music Player")
        self.assertTrue(bg_music_window.exists(), "Background Music Player window did not open.")

        # Set main player volume
        main_vol_control = self.main_window.SpinControl
        main_vol_control.set_text("80")
        time.sleep(0.5)
        self.main_window.type_keys("{ENTER}") # To ensure value is set
        time.sleep(0.5)

        # Set background music player volume
        bg_vol_control = bg_music_window.Slider
        bg_vol_control.set_value(30)
        time.sleep(0.5)
        # Assuming the slider automatically updates the volume, or there's a different control.
        # If there's an 'Apply' button or ENTER key needed for the background window, add it here.

        # Verify volumes (this part needs to be improved based on actual UI elements to read volume)
        # For now, we'll just check if the controls have different values.
        # Ideally, we'd read the actual volume from the VLC instances, but pywinauto can't do that.
        # We are asserting that setting one doesn't immediately reflect in the other's control.

        # Main window's volume control should still show 80
        self.assertEqual(main_vol_control.get_value(), 80, "Main player volume changed unexpectedly.")

        # Background music window's volume control should still show 30
        self.assertEqual(bg_vol_control.get_value(), 30, "Background music volume changed unexpectedly.")

        # Close background music window
        bg_music_window.close()
        time.sleep(0.5)

    def tearDown(self):
        if self.app and self.app.is_process_running():
            self.main_window.close()
            self.app.wait_for_process_exit(timeout=5)
        # Clean up last_fest.txt if it exists
        if os.path.isfile("last_fest.txt"):
            os.remove("last_fest.txt")
        # Clean up backup files from test data directory
        for backup in glob.glob(os.path.join(os.path.split(sample_fest_path)[0], "*.bkp.fest")):
            os.remove(backup)


if __name__ == '__main__':
    unittest.main()

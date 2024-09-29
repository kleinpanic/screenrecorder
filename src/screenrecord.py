import os
import subprocess
import tkinter as tk
from tkinter import simpledialog, messagebox
import time
import ffmpeg
import cv2
from PIL import Image, ImageTk
import threading


class ScreenRecorder:
    def __init__(self, root, control_frame):
        self.root = root
        self.is_recording = False
        self.start_time = None
        self.output_dir = f"{os.environ['HOME']}/Videos/Screenrecords"
        self.video_file = None
        self.audio_file = None
        self.final_file = None
        self.video_proc = None
        self.audio_proc = None
        self.recording_thread = None

        self.audio_devices = ['hw:0,7', 'hw:0,6']  # List of audio devices
        self.current_device_index = 0

        # Place the start/stop button in the control frame
        self.toggle_button = tk.Button(control_frame, text="Start", command=self.toggle_recording, width=15, height=2)
        self.toggle_button.grid(row=0, column=0, padx=10)

        # Other labels and components can be packed in the main window
        self.status_label = tk.Label(root, text="Status: Stopped", anchor='w')
        self.status_label.pack(fill='x', padx=10, pady=5)

        self.mic_label = tk.Label(root, text="Mic: ALSA (hw:0,7)", anchor='w')
        self.mic_label.pack(fill='x', padx=10, pady=5)

        self.time_label = tk.Label(root, text="Recording Time: 0s", anchor='w')
        self.time_label.pack(fill='x', padx=10, pady=5)

        self.size_label = tk.Label(root, text="File Size: 0 MB", anchor='w')
        self.size_label.pack(fill='x', padx=10, pady=5)

        self.duration_label = tk.Label(root, text="Duration: N/A", anchor='w')
        self.duration_label.pack(fill='x', padx=10, pady=5)

        self.resolution_label = tk.Label(root, text="Resolution: N/A", anchor='w')
        self.resolution_label.pack(fill='x', padx=10, pady=5)

        self.video_codec_label = tk.Label(root, text="Video Codec: N/A", anchor='w')
        self.video_codec_label.pack(fill='x', padx=10, pady=5)

        self.audio_codec_label = tk.Label(root, text="Audio Codec: N/A", anchor='w')
        self.audio_codec_label.pack(fill='x', padx=10, pady=5)

        self.update_info()

    def toggle_recording(self):
        if self.is_recording:
            self.stop_recording()
        else:
            self.start_recording()

    def start_recording(self):
        # Start the recording in a separate thread
        self.recording_thread = threading.Thread(target=self._start_recording)
        self.recording_thread.start()

    def _start_recording(self):
        self.is_recording = True
        self.start_time = time.time()
        self.root.after(0, lambda: self.status_label.config(text="Status: Recording"))
        self.root.after(0, lambda: self.toggle_button.config(text="Stop"))

        # Generate temporary filenames for the recording
        self.video_file = os.path.join(self.output_dir, "temp_video.mp4")
        self.audio_file = os.path.join(self.output_dir, "temp_audio.wav")

        # Start the video recording process
        self.video_proc = subprocess.Popen([
            'ffmpeg', '-f', 'x11grab', '-s', '1920x1080', '-i', os.environ['DISPLAY'],
            '-c:v', 'libx264', '-r', '30', '-preset', 'ultrafast', self.video_file
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        # Try starting the audio recording process
        self.start_audio_recording()

        self.update_info()

    def start_audio_recording(self):
        success = False
        for i in range(len(self.audio_devices)):
            self.current_device_index = i
            try:
                # Try using the current audio device
                self.audio_proc = subprocess.Popen([
                    'arecord', '-D', self.audio_devices[self.current_device_index], '-f', 'cd', '-t', 'wav', '-r', '16000', self.audio_file
                ], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)

                # Allow time for the process to initialize
                time.sleep(3)
                if self.audio_proc.poll() is not None:
                    raise Exception(f"Audio device {self.audio_devices[self.current_device_index]} failed to start.")

                success = True
                self.root.after(0, lambda: self.mic_label.config(text=f"Mic: ALSA ({self.audio_devices[self.current_device_index]})"))
                break
            except Exception as e:
                print(f"Error with audio device {self.audio_devices[self.current_device_index]}: {e}")
                if self.audio_proc:
                    self.audio_proc.terminate()

        if not success:
            self.root.after(0, lambda: messagebox.showerror("Audio Recording Failed", "Both audio devices failed. Exiting the program."))
            self.root.quit()

    def stop_recording(self):
        if self.video_proc:
            self.video_proc.terminate()
            try:
                self.video_proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.video_proc.kill()

        if self.audio_proc:
            self.audio_proc.terminate()
            try:
                self.audio_proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.audio_proc.kill()

        self.is_recording = False
        self.root.after(0, lambda: self.status_label.config(text="Status: Stopped"))
        self.root.after(0, lambda: self.toggle_button.config(text="Start"))

        if self.recording_thread and self.recording_thread.is_alive():
            self.recording_thread.join()

        self.combine_audio_video()

    def combine_audio_video(self):
        # Prompt for file name
        file_name = simpledialog.askstring("Save Recording", "Enter file name (leave blank for default):")

        if not file_name:
            # Generate default file name
            existing_files = [f for f in os.listdir(self.output_dir) if f.startswith("screenrecording") and f.endswith(".mp4")]
            next_number = len(existing_files) + 1
            file_name = f"screenrecording{next_number}.mp4"
        else:
            file_name += ".mp4"

        self.final_file = os.path.join(self.output_dir, file_name)

        # Combine audio and video
        subprocess.run([
            'ffmpeg', '-i', self.video_file, '-i', self.audio_file, '-c:v', 'copy', '-c:a', 'aac', self.final_file
        ], stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        # Remove the temporary video and audio files
        if os.path.exists(self.video_file):
            os.remove(self.video_file)
        if os.path.exists(self.audio_file):
            os.remove(self.audio_file)

        self.display_mp4_info()
        self.root.after(0, lambda: self.status_label.config(text=f"Saved as {file_name}"))

    def display_mp4_info(self):
        try:
            probe = ffmpeg.probe(self.final_file)
            video_info = next(stream for stream in probe['streams'] if stream['codec_type'] == 'video')
            audio_info = next(stream for stream in probe['streams'] if stream['codec_type'] == 'audio')

            duration = float(probe['format']['duration'])
            self.root.after(0, lambda: self.duration_label.config(text=f"Duration: {duration:.2f} seconds"))

            resolution = f"{video_info['width']}x{video_info['height']}"
            self.root.after(0, lambda: self.resolution_label.config(text=f"Resolution: {resolution}"))

            video_codec = video_info['codec_name']
            self.root.after(0, lambda: self.video_codec_label.config(text=f"Video Codec: {video_codec}"))

            audio_codec = audio_info['codec_name']
            self.root.after(0, lambda: self.audio_codec_label.config(text=f"Audio Codec: {audio_codec}"))

        except Exception as e:
            print(f"Error displaying MP4 info: {e}")

    def update_info(self):
        if self.is_recording:
            elapsed_time = int(time.time() - self.start_time)
            self.root.after(0, lambda: self.time_label.config(text=f"Recording Time: {elapsed_time}s"))

            if os.path.exists(self.video_file):
                size_mb = os.path.getsize(self.video_file) / (1024 * 1024)
                self.root.after(0, lambda: self.size_label.config(text=f"File Size: {size_mb:.2f} MB"))
            else:
                self.root.after(0, lambda: self.size_label.config(text="File Size: 0 MB"))

        self.root.after(1000, self.update_info)


class CameraRecorder:
    def __init__(self, root, control_frame):
        self.root = root
        self.camera_on = False
        self.cap = None

        # Button to start/stop camera, placed in the control frame
        self.camera_button = tk.Button(control_frame, text="Start Camera", command=self.toggle_camera, width=15, height=2)
        self.camera_button.grid(row=0, column=1, padx=10)

        # Label to display camera feed
        self.camera_frame = tk.Label(root)
        self.camera_frame.pack(pady=10)

    def toggle_camera(self):
        if self.camera_on:
            self.stop_camera()
        else:
            self.start_camera()

    def start_camera(self):
        if messagebox.askyesno("Start Camera", "Are you sure you want to turn on the camera?"):
            self.cap = cv2.VideoCapture(0)  # Open the default camera
            if not self.cap.isOpened():
                messagebox.showerror("Camera Error", "Unable to access the camera.")
                return
            self.camera_on = True
            self.camera_button.config(text="Stop Camera")
            self.update_camera()

    def stop_camera(self):
        if self.cap:
            self.camera_on = False
            self.cap.release()
            self.camera_button.config(text="Start Camera")
            self.camera_frame.config(image='')  # Clear the camera frame

    def update_camera(self):
        if self.camera_on:
            ret, frame = self.cap.read()
            if ret:
                # Convert the frame to RGB and display it
                cv2image = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                img = Image.fromarray(cv2image)
                imgtk = ImageTk.PhotoImage(image=img)
                self.camera_frame.imgtk = imgtk
                self.camera_frame.config(image=imgtk)

            self.root.after(10, self.update_camera)


def main():
    root = tk.Tk()
    root.geometry("450x500")  # Increase the window size to fit all elements

    # Create a frame to hold the control buttons
    control_frame = tk.Frame(root)
    control_frame.pack(pady=10)

    # Initialize ScreenRecorder and place its button in the control_frame
    screen_recorder = ScreenRecorder(root, control_frame)

    # Initialize CameraRecorder and place its button in the control_frame
    camera_recorder = CameraRecorder(root, control_frame)

    # Bind the 'Q' and 'Esc' keys to exit the application globally
    def quit_app(event=None):
        if not screen_recorder.is_recording and not camera_recorder.camera_on:
            root.destroy()

    root.bind('<Escape>', quit_app)
    root.bind('<q>', quit_app)

    root.mainloop()


if __name__ == "__main__":
    main()

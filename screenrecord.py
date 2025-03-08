#!/usr/bin/env python3
import os
import re
import subprocess
import tkinter as tk
from tkinter import simpledialog, messagebox, ttk
import time
import ffmpeg
import cv2
from PIL import Image, ImageTk
import threading
import signal
import sys

def get_monitor_geometry(monitor_name):
    """
    Query xrandr to get the geometry for the given monitor.
    Returns a tuple (resolution, offset) where resolution is "WxH" and
    offset is in the form "+X+Y". Returns (None, None) if not found.
    """
    try:
        output = subprocess.check_output(["xrandr", "--query"], universal_newlines=True)
        for line in output.splitlines():
            if " connected" in line and monitor_name.lower() in line.lower():
                m = re.search(r'(\d+x\d+\+\d+\+\d+)', line)
                if m:
                    geom = m.group(1)  # e.g. "1920x1080+0+0"
                    parts = geom.split('+')
                    if len(parts) >= 3:
                        resolution = parts[0]      # "1920x1080"
                        offset = f"+{parts[1]}+{parts[2]}"
                        return resolution, offset
        return None, None
    except Exception as e:
        print("Error querying xrandr:", e)
        return None, None

def select_window_geometry(root):
    """
    Uses xwininfo so the user can click on a window.
    Returns a geometry string in the format "X,Y,W,H" on success or None on error.
    """
    try:
        output = subprocess.check_output(["xwininfo"], universal_newlines=True)
        x_match = re.search(r'Absolute upper-left X:\s+(\d+)', output)
        y_match = re.search(r'Absolute upper-left Y:\s+(\d+)', output)
        w_match = re.search(r'Width:\s+(\d+)', output)
        h_match = re.search(r'Height:\s+(\d+)', output)
        if x_match and y_match and w_match and h_match:
            x = int(x_match.group(1))
            y = int(y_match.group(1))
            w = int(w_match.group(1))
            h = int(h_match.group(1))
            geometry = f"{x},{y},{w},{h}"
            messagebox.showinfo("Window Selected", f"Selected window geometry: {geometry}", parent=root)
            return geometry
        else:
            messagebox.showerror("Selection Error", "Could not parse window geometry.", parent=root)
            return None
    except Exception as e:
        messagebox.showerror("Window Selection Error", f"Error selecting window:\n{e}", parent=root)
        return None

class ScreenRecorder:
    def __init__(self, root, record_btn, pause_btn, info_frame):
        self.root = root
        self.record_btn = record_btn      # Reference to the record button (for updating text)
        self.pause_btn = pause_btn        # Reference to the pause/resume button
        self.info_frame = info_frame

        self.is_recording = False         # Overall recording state
        self.paused = False               # Pause state within a recording
        self.start_time = None            # Overall start time
        self.output_dir = os.path.join(os.environ['HOME'], "Videos", "Screenrecords")
        os.makedirs(self.output_dir, exist_ok=True)
        self.segments = []                # List of segment file paths
        self.current_segment_proc = None  # ffmpeg process for current segment
        self.current_segment_file = None  # Filename for current segment

        # Fixed default audio device order.
        self.audio_devices = ['hw:0,7', 'hw:0,6']

        # For "Window" source selection.
        self.selected_window_geometry = None

        # Retrieve info labels by name.
        self.status_label = info_frame.nametowidget("status_label")
        self.mic_label = info_frame.nametowidget("mic_label")
        self.time_label = info_frame.nametowidget("time_label")
        self.size_label = info_frame.nametowidget("size_label")
        self.duration_label = info_frame.nametowidget("duration_label")
        self.resolution_label = info_frame.nametowidget("resolution_label")
        self.video_codec_label = info_frame.nametowidget("video_codec_label")
        self.audio_codec_label = info_frame.nametowidget("audio_codec_label")

        self.update_info()

    def toggle_recording(self):
        if not self.is_recording:
            # Start a new recording session.
            self.segments = []
            self.paused = False
            self.start_time = time.time()
            self.set_status("Recording")
            self.record_btn.config(text="Stop Recording")
            self.pause_btn.config(text="Pause Recording", state="normal")
            self._start_segment()
            self.is_recording = True
        else:
            # Stop current segment if running.
            if self.current_segment_proc:
                self._stop_current_segment()
            self.is_recording = False
            self.set_status("Stopped")
            self.record_btn.config(text="Start Recording")
            self.pause_btn.config(text="Pause Recording", state="disabled")
            self._combine_segments()

    def toggle_pause(self):
        if not self.is_recording:
            return
        if not self.paused:
            # Pause: stop the current segment.
            if self.current_segment_proc:
                self._stop_current_segment()
            self.paused = True
            self.pause_btn.config(text="Resume Recording")
            self.set_status("Paused")
        else:
            # Resume: start a new segment.
            self._start_segment()
            self.paused = False
            self.pause_btn.config(text="Pause Recording")
            self.set_status("Recording")

    def _start_segment(self):
        """
        Starts a new ffmpeg process to record a segment with combined audio and video.
        Uses the selected recording source and quality.
        """
        # Get options from the GUI variables.
        source_option = self.source_var.get() if hasattr(self, 'source_var') else "Entire Desktop"
        quality_option = self.quality_var.get() if hasattr(self, 'quality_var') else "Medium"

        # Determine capture settings.
        if source_option == "Entire Desktop":
            width = self.root.winfo_screenwidth()
            height = self.root.winfo_screenheight()
            resolution = f"{width}x{height}"
            display_input = os.environ.get('DISPLAY', ':0.0') + "+0+0"
        elif source_option in ["eDP-1", "HDMI-1"]:
            res, offset = get_monitor_geometry(source_option)
            if res is None:
                messagebox.showerror("Monitor Error",
                                     f"Could not get geometry for monitor {source_option}",
                                     parent=self.root)
                return
            resolution = res
            display_input = os.environ.get('DISPLAY', ':0.0') + offset
        elif source_option == "Window":
            if self.selected_window_geometry is None:
                messagebox.showerror("Window Not Selected", "Please click the 'Select Window' button.", parent=self.root)
                return
            try:
                parts = [int(x.strip()) for x in self.selected_window_geometry.split(',')]
                if len(parts) != 4:
                    raise ValueError("Invalid format")
                x, y, w, h = parts
                resolution = f"{w}x{h}"
                display_input = f"{os.environ.get('DISPLAY', ':0.0')}+{x}+{y}"
            except Exception:
                messagebox.showerror("Window Geometry Error", "Invalid window geometry.", parent=self.root)
                return
        else:
            width = self.root.winfo_screenwidth()
            height = self.root.winfo_screenheight()
            resolution = f"{width}x{height}"
            display_input = os.environ.get('DISPLAY', ':0.0') + "+0+0"

        # Map quality setting.
        if quality_option.lower() == "low":
            preset = "ultrafast"
            crf = "30"
        elif quality_option.lower() == "high":
            preset = "slow"
            crf = "18"
        else:
            preset = "medium"
            crf = "23"

        # Use first audio device.
        audio_dev = self.audio_devices[0]

        self.resolution_value = resolution

        # Create a new segment file.
        seg_index = len(self.segments) + 1
        seg_filename = os.path.join(self.output_dir, f"segment_{seg_index}.mp4")
        self.current_segment_file = seg_filename
        cmd = [
            'ffmpeg',
            '-f', 'x11grab',
            '-video_size', resolution,
            '-i', display_input,
            '-f', 'alsa',
            '-thread_queue_size', '512',  # Helps with buffering
            '-i', audio_dev,
            '-c:v', 'libx264',
            '-preset', preset,
            '-crf', crf,
            '-r', '30',
            '-c:a', 'aac',
            '-ar', '44100',  # Set sample rate explicitly
            '-ac', '2',      # Force stereo audio
            seg_filename
        ]
        self.current_segment_proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def _stop_current_segment(self):
        """
        Stops the current ffmpeg process (if any) and adds its file to the segments list.
        """
        if self.current_segment_proc:
            self.current_segment_proc.terminate()
            try:
                # self.current_segment_proc.wait(timeout=5)
                self.current_segment_proc.communicate(input=b"q", timeout=5)
            except subprocess.TimeoutExpired:
                self.current_segment_proc.kill()
            self.segments.append(self.current_segment_file)
            self.current_segment_proc = None
            self.current_segment_file = None

    def _combine_segments(self):
        """
        Combines all recorded segments into a final file using ffmpeg's concat demuxer
        and re-encodes the result to fix timestamp issues.
        """
        if not self.segments:
            messagebox.showerror("No Segments", "No recording segments were recorded.", parent=self.root)
            return
        list_filename = os.path.join(self.output_dir, "segments.txt")
        with open(list_filename, "w") as f:
            for seg in self.segments:
                f.write(f"file '{seg}'\n")
        file_name = simpledialog.askstring("Save Recording",
                                             "Enter file name (leave blank for default):",
                                             parent=self.root)
        if not file_name:
            existing = [f for f in os.listdir(self.output_dir) if f.startswith("screenrecording") and f.endswith(".mp4")]
            file_name = f"screenrecording{len(existing)+1}.mp4"
        else:
            file_name += ".mp4"
        final_file = os.path.join(self.output_dir, file_name)
        cmd = [
            'ffmpeg',
            '-fflags', '+genpts',           # Generate new PTS for all frames
            '-f', 'concat',
            '-safe', '0',
            '-i', list_filename,
            '-vsync', '2',                  # Adjust video sync method
            '-c:v', 'libx264',
            '-preset', 'medium',
            '-crf', '23',
            '-c:a', 'aac',
            '-af', 'aresample=async=1',      # Resample audio for sync issues
            '-ar', '44100',                # Explicitly set sample rate
            '-ac', '2',                    # Force stereo output
            final_file
        ]

        subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        for seg in self.segments:
            if os.path.exists(seg):
                os.remove(seg)
        os.remove(list_filename)
        self.set_status(f"Saved as {file_name}")
        try:
            probe = ffmpeg.probe(final_file)
            video_info = next(stream for stream in probe['streams'] if stream['codec_type'] == 'video')
            audio_info = next(stream for stream in probe['streams'] if stream['codec_type'] == 'audio')
            duration = float(probe['format']['duration'])
            resolution = f"{video_info['width']}x{video_info['height']}"
            video_codec = video_info['codec_name']
            audio_codec = audio_info['codec_name']
            self.duration_label.config(text=f"Duration: {duration:.2f} sec")
            self.resolution_label.config(text=f"Resolution: {resolution}")
            self.video_codec_label.config(text=f"Video Codec: {video_codec}")
            self.audio_codec_label.config(text=f"Audio Codec: {audio_codec}")
        except Exception as e:
            print(f"Error displaying final info: {e}")

    def set_status(self, text):
        self.status_label.config(text=f"Status: {text}")

    def update_info(self):
        if self.is_recording and not self.paused:
            elapsed = int(time.time() - self.start_time)
            self.time_label.config(text=f"Recording Time: {elapsed}s")
            total_size = 0
            for seg in self.segments:
                if os.path.exists(seg):
                    total_size += os.path.getsize(seg)
            if self.current_segment_file and os.path.exists(self.current_segment_file):
                total_size += os.path.getsize(self.current_segment_file)
            self.size_label.config(text=f"File Size: {total_size/1024/1024:.2f} MB")
        self.root.after(1000, self.update_info)

class CameraRecorder:
    def __init__(self, root, cam_btn, camera_frame):
        self.root = root
        self.camera_btn = cam_btn
        self.camera_frame = camera_frame
        self.camera_on = False
        self.cap = None
        self.resized = False

    def toggle_camera(self):
        if self.camera_on:
            self.stop_camera()
        else:
            self.start_camera()

    def start_camera(self):
        if messagebox.askyesno("Start Camera", "Turn on the camera?", parent=self.root):
            self.cap = cv2.VideoCapture(0)
            if not self.cap.isOpened():
                messagebox.showerror("Camera Error", "Unable to access the camera.", parent=self.root)
                return
            self.camera_on = True
            self.camera_btn.config(text="Stop Camera")
            self.camera_frame.pack(side="right", padx=10, pady=10)
            self.update_camera()

    def stop_camera(self):
        if self.cap:
            self.camera_on = False
            self.cap.release()
            self.camera_btn.config(text="Start Camera")
            self.camera_frame.pack_forget()
            self.resized = False

    def update_camera(self):
        if self.camera_on:
            ret, frame = self.cap.read()
            if ret:
                cv2image = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                img = Image.fromarray(cv2image)
                imgtk = ImageTk.PhotoImage(image=img)
                self.camera_frame.imgtk = imgtk
                self.camera_frame.config(image=imgtk)
                if not self.resized:
                    new_size = 320
                    self.root.geometry(f"{new_size+400}x{new_size+150}")
                    self.resized = True
            self.root.after(10, self.update_camera)

def quit_app(event=None, screen_recorder=None, camera_recorder=None, root=None):
    if screen_recorder and camera_recorder:
        if screen_recorder.is_recording or camera_recorder.camera_on:
            if not messagebox.askyesno("Quit", "Recording or camera is active. Quit anyway?", parent=root):
                return
    root.destroy()

def main():
    root = tk.Tk()
    root.title("Screen Recorder")
    root.geometry("600x400")

    style = ttk.Style()
    style.theme_use('clam')
    style.configure("TFrame", background="#e0f7fa")
    style.configure("TLabel", background="#e0f7fa", font=("Helvetica", 10))
    style.configure("TButton", background="#00796b", foreground="white", font=("Helvetica", 10, "bold"))

    main_frame = ttk.Frame(root)
    main_frame.pack(fill="both", expand=True)

    banner_frame = ttk.Frame(main_frame)
    banner_frame.pack(side="top", fill="x", padx=10, pady=10)
    banner_label = ttk.Label(banner_frame, text="Screen Recorder", font=("Helvetica", 16, "bold"))
    banner_label.pack()

    options_frame = ttk.Frame(main_frame)
    options_frame.pack(side="top", fill="x", padx=10, pady=10)
    src_label = ttk.Label(options_frame, text="Recording Source:")
    src_label.grid(row=0, column=0, padx=5, pady=5, sticky="w")
    source_var = tk.StringVar(value="Entire Desktop")
    src_dropdown = ttk.Combobox(options_frame, textvariable=source_var,
                                values=["Entire Desktop", "eDP-1", "HDMI-1", "Window"],
                                state="readonly", width=15)
    src_dropdown.grid(row=0, column=1, padx=5, pady=5)
    qual_label = ttk.Label(options_frame, text="Recording Quality:")
    qual_label.grid(row=1, column=0, padx=5, pady=5, sticky="w")
    quality_var = tk.StringVar(value="Medium")
    qual_dropdown = ttk.Combobox(options_frame, textvariable=quality_var,
                                 values=["Low", "Medium", "High"],
                                 state="readonly", width=15)
    qual_dropdown.grid(row=1, column=1, padx=5, pady=5)
    select_window_btn = ttk.Button(options_frame, text="Select Window",
                                   command=lambda: setattr(screen_recorder, 'selected_window_geometry', select_window_geometry(root)))
    select_window_btn.grid(row=2, column=0, columnspan=2, padx=5, pady=5)
    select_window_btn.grid_remove()
    def on_src_change(event):
        if source_var.get() == "Window":
            select_window_btn.grid()
        else:
            select_window_btn.grid_remove()
    src_dropdown.bind("<<ComboboxSelected>>", on_src_change)

    bottom_frame = ttk.Frame(main_frame)
    bottom_frame.pack(side="bottom", fill="x", padx=10, pady=10)
    info_frame = ttk.Frame(bottom_frame)
    info_frame.pack(side="top", fill="x", pady=5)
    status_lbl = ttk.Label(info_frame, text="Status: Stopped", name="status_label")
    status_lbl.grid(row=0, column=0, sticky="w", padx=5, pady=2)
    mic_lbl = ttk.Label(info_frame, text="Mic: ALSA (hw:0,7)", name="mic_label")
    mic_lbl.grid(row=1, column=0, sticky="w", padx=5, pady=2)
    time_lbl = ttk.Label(info_frame, text="Recording Time: 0s", name="time_label")
    time_lbl.grid(row=2, column=0, sticky="w", padx=5, pady=2)
    size_lbl = ttk.Label(info_frame, text="File Size: 0 MB", name="size_label")
    size_lbl.grid(row=3, column=0, sticky="w", padx=5, pady=2)
    dur_lbl = ttk.Label(info_frame, text="Duration: N/A", name="duration_label")
    dur_lbl.grid(row=4, column=0, sticky="w", padx=5, pady=2)
    res_lbl = ttk.Label(info_frame, text="Resolution: N/A", name="resolution_label")
    res_lbl.grid(row=5, column=0, sticky="w", padx=5, pady=2)
    vid_codec_lbl = ttk.Label(info_frame, text="Video Codec: N/A", name="video_codec_label")
    vid_codec_lbl.grid(row=6, column=0, sticky="w", padx=5, pady=2)
    aud_codec_lbl = ttk.Label(info_frame, text="Audio Codec: N/A", name="audio_codec_label")
    aud_codec_lbl.grid(row=7, column=0, sticky="w", padx=5, pady=2)

    buttons_frame = ttk.Frame(bottom_frame)
    buttons_frame.pack(side="bottom", fill="x", pady=5)
    record_btn = ttk.Button(buttons_frame, text="Start Recording")
    record_btn.pack(side="left", padx=10, pady=5)
    pause_btn = ttk.Button(buttons_frame, text="Pause Recording", state="disabled")
    pause_btn.pack(side="left", padx=10, pady=5)
    cam_btn = ttk.Button(buttons_frame, text="Start Camera")
    cam_btn.pack(side="left", padx=10, pady=5)

    cam_feed_frame = ttk.Label(main_frame)
    cam_feed_frame.pack_forget()

    screen_recorder = ScreenRecorder(root, record_btn, pause_btn, info_frame)
    camera_recorder = CameraRecorder(root, cam_btn, cam_feed_frame)
    screen_recorder.source_var = source_var
    screen_recorder.quality_var = quality_var

    record_btn.config(command=screen_recorder.toggle_recording)
    pause_btn.config(command=screen_recorder.toggle_pause)
    cam_btn.config(command=camera_recorder.toggle_camera)

    root.bind('<Escape>', lambda event: quit_app(event, screen_recorder, camera_recorder, root))
    root.bind('<q>', lambda event: quit_app(event, screen_recorder, camera_recorder, root))

    def sigint_handler(sig, frame):
        print("Caught SIGINT, exiting gracefully...")
        if screen_recorder.is_recording:
            screen_recorder.toggle_recording()  # Stops recording.
        if camera_recorder.camera_on:
            camera_recorder.stop_camera()
        root.quit()
        sys.exit(0)
    signal.signal(signal.SIGINT, sigint_handler)

    root.mainloop()

if __name__ == "__main__":
    main()


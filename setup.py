#!/usr/bin/env python3
import argparse
import subprocess
import os
import shutil
import sys
import sysconfig

VERSION = "1.0.7"

HOOK_FILENAME = "hook-ffmpeg.py"
# This hook is used by PyInstaller. It tells PyInstaller to treat "ffmpeg" as a hidden import.
# (PyInstaller sometimes misses modules that are single-file or not recognized as packages.)
HOOK_CONTENT = "hiddenimports = ['ffmpeg']\n"

# Global flag to know if we created the hook file (so we can delete it later)
created_hook = False

def create_ffmpeg_hook():
    """Create a hook file for ffmpeg in the current directory if it doesn't already exist."""
    global created_hook
    if not os.path.exists(HOOK_FILENAME):
        with open(HOOK_FILENAME, "w", encoding="utf-8") as hook_file:
            hook_file.write(HOOK_CONTENT)
        print(f"Created hook file: {HOOK_FILENAME}")
        created_hook = True

def get_extra_pyinstaller_args():
    """
    Returns a list of extra arguments for PyInstaller:
      - Forces inclusion of the ffmpeg module.
      - Adds our additional hooks directory.
      - Adds the Python shared library using the correct INSTSONAME.
    """
    extra_args = [
        "--hidden-import", "ffmpeg",
        "--collect-submodules", "ffmpeg",
        "--additional-hooks-dir", "."
    ]
    
    instsoname = sysconfig.get_config_var("INSTSONAME")  # e.g., libpython3.11.so.1.0
    if instsoname:
        libdir = sysconfig.get_config_var("LIBDIR")
        libpython_path = os.path.join(libdir, instsoname) if libdir else None
        if not libpython_path or not os.path.exists(libpython_path):
            fallback = os.path.join("/usr/lib/x86_64-linux-gnu", instsoname)
            if os.path.exists(fallback):
                libpython_path = fallback
        if libpython_path and os.path.exists(libpython_path):
            extra_args.extend(["--add-binary", f"{libpython_path}:."])
        else:
            print("Warning: Could not locate the Python shared library.")
    return extra_args

def build_binary():
    """
    Builds a one-file binary from screenrecord.py using PyInstaller.
    Attempts:
      1. A locally installed PyInstaller.
      2. pipx if available.
      3. Installing PyInstaller in a virtual environment (with --break-system-packages).
    Returns True on success, False otherwise.
    """
    create_ffmpeg_hook()
    pyinstaller_args = ["--onefile"] + get_extra_pyinstaller_args() + ["screenrecord.py"]

    # Try using a locally installed PyInstaller.
    try:
        import PyInstaller.__main__
        print("Using locally installed PyInstaller.")
        PyInstaller.__main__.run(pyinstaller_args)
        return True
    except ImportError:
        pass

    # Try using pipx.
    if shutil.which("pipx"):
        print("PyInstaller not found locally. Using pipx to run PyInstaller.")
        try:
            cmd = ["pipx", "run", "pyinstaller"] + pyinstaller_args
            subprocess.check_call(cmd)
            return True
        except subprocess.CalledProcessError:
            print("Error: 'pipx run pyinstaller' failed.")
            return False

    # If pipx isn't available, check if we're in a virtual environment.
    if os.environ.get("VIRTUAL_ENV") is not None:
        print("In a virtual environment. Installing PyInstaller using pip with --break-system-packages...")
        try:
            subprocess.check_call(
                [sys.executable, "-m", "pip", "install", "--break-system-packages", "pyinstaller"]
            )
        except subprocess.CalledProcessError:
            print("Error: Failed to install PyInstaller in the virtual environment.")
            return False

        try:
            import PyInstaller.__main__
            PyInstaller.__main__.run(pyinstaller_args)
            return True
        except Exception as e:
            print("Error: PyInstaller run failed after installation in venv:", e)
            return False

    print("Error: PyInstaller is not installed and neither pipx nor a virtual environment is available.")
    print("Please install pipx or run this installer in a virtual environment, then try again.")
    return False

def cleanup():
    """Remove temporary build files and our hook file if we created it."""
    dirs_to_remove = ["build"]
    files_to_remove = [HOOK_FILENAME, "screenrecord.spec"]
    
    for d in dirs_to_remove:
        if os.path.isdir(d):
            try:
                shutil.rmtree(d)
                print(f"Removed directory: {d}")
            except Exception as e:
                print(f"Warning: Could not remove directory {d}: {e}")
                
    for f in files_to_remove:
        if os.path.exists(f):
            try:
                os.remove(f)
                print(f"Removed file: {f}")
            except Exception as e:
                print(f"Warning: Could not remove file {f}: {e}")

def install():
    print("Building binary with PyInstaller...")
    if not build_binary():
        sys.exit(1)

    # Determine the binary name; PyInstaller typically creates "screenrecord" in the dist folder.
    binary_name = "screenrecord"
    dist_path = os.path.join("dist", binary_name)
    if not os.path.exists(dist_path):
        # As a fallback, check for a .py extension.
        dist_path = os.path.join("dist", "screenrecord.py")
        if not os.path.exists(dist_path):
            print("Error: Binary not found in the 'dist' folder after build.")
            sys.exit(1)

    print(f"Built binary located at: {dist_path}")
    confirm = input("Do you want to move the binary to ~/.local/bin for global access? [y/N]: ")
    if confirm.lower() in ["y", "yes"]:
        local_bin = os.path.expanduser("~/.local/bin")
        os.makedirs(local_bin, exist_ok=True)
        destination = os.path.join(local_bin, binary_name)
        try:
            shutil.move(dist_path, destination)
            print(f"Installation successful! Binary moved to {destination}")
        except Exception as e:
            print(f"Error moving binary to {destination}: {e}")
            sys.exit(1)
    else:
        print("Installation complete. The binary remains in the 'dist' folder.")
        
    # Cleanup temporary files created by PyInstaller and this installer.
    cleanup()

def uninstall():
    local_bin = os.path.expanduser("~/.local/bin")
    binary_path = os.path.join(local_bin, "screenrecord")
    if os.path.exists(binary_path):
        try:
            os.remove(binary_path)
            print(f"Uninstalled: Removed {binary_path}")
        except Exception as e:
            print(f"Error removing {binary_path}: {e}")
            sys.exit(1)
    else:
        print("Uninstall: 'screenrecord' binary not found in ~/.local/bin.")

def main():
    parser = argparse.ArgumentParser(description="Installer for screenrecord.py")
    parser.add_argument("command", choices=["install", "uninstall", "version", "help"],
                        help="Command: install, uninstall, version, or help")
    args = parser.parse_args()

    if args.command == "install":
        install()
    elif args.command == "uninstall":
        uninstall()
    elif args.command == "version":
        print(f"screenrecord installer version {VERSION}")
    elif args.command == "help":
        parser.print_help()

if __name__ == "__main__":
    main()


import os
import time
import subprocess
import psutil
from obswebsocket import obsws, requests
import json

class AutoOBSRecorder:
    def __init__(self, password="6u6vcNXZKyFmE98S", port=4455):
        """Initialize automatic OBS recorder"""
        self.password = password
        self.port = port
        self.ws = None
        self.connected = False
        self.obs_process = None
        
        # Paths for OBS
        self.obs_paths = [
            "C:\\Program Files\\obs-studio\\bin\\64bit\\obs64.exe"
           # "C:\\ProgramData\\Microsoft\\Windows\\Start Menu\\Programs"
            # "C:\\Program Files\\obs-studio\\bin\\64bit\\obs64.exe",
            # "C:\\Program Files\\obs-studio\\bin\\32bit\\obs32.exe",
            # "C:\\Program Files (x86)\\obs-studio\\bin\\64bit\\obs64.exe",
            # "C:\\Program Files (x86)\\obs-studio\\bin\\32bit\\obs32.exe",
            # os.path.expanduser("~\\AppData\\Local\\Programs\\obs-studio\\bin\\64bit\\obs64.exe"),
        ]
        
        # VSCode project folder
        self.project_folder = os.getcwd()
        self.recordings_folder = os.path.join(self.project_folder, "zoom_recordings")
        
    def is_obs_running(self):
        """Check if OBS is already running"""
        for proc in psutil.process_iter(['name']):
            if proc.info['name'] and 'obs' in proc.info['name'].lower():
                return True
        return False
    
    def find_obs_path(self):
        """Find OBS installation path"""
        for path in self.obs_paths:
            if os.path.exists(path):
                print(f"✅ Found OBS at: {path}")
                return path
        
        # Try to find in PATH
        try:
            result = subprocess.run(['where', 'obs64.exe'], capture_output=True, text=True)
            if result.returncode == 0 and result.stdout.strip():
                print(f"✅ Found OBS in PATH: {result.stdout.strip()}")
                return result.stdout.strip()
        except:
            pass
        
        print("❌ Could not find OBS Studio")
        return None
    
    def start_obs(self):
        """Start OBS Studio"""
        print("🚀 Starting OBS Studio...")
        
        # Check if already running
        if self.is_obs_running():
            print("✅ OBS is already running")
            return True
        
        # Find OBS path
        obs_exe = self.find_obs_path()
        if not obs_exe:
            print("❌ Please install OBS Studio from: https://obsproject.com/")
            return False
        
        # Start OBS
        try:
            # Start with WebSocket parameters in config (requires pre-configuration)
            
            self.obs_process = subprocess.Popen(
            [obs_exe],
            cwd=os.path.dirname(obs_exe),   # <<< Critical fix
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
            print("✅ OBS started")
            
            # Wait for OBS to load
            print("⏳ Waiting for OBS to start (10 seconds)...")
            time.sleep(10)
            
            # Check if OBS is now running
            if self.is_obs_running():
                return True
            else:
                print("❌ OBS failed to start")
                return False
                
        except Exception as e:
            print(f"❌ Failed to start OBS: {e}")
            return False
    
    def configure_obs_via_cli(self):
        """Configure OBS using CLI/Config file method"""
        print("⚙️ Configuring OBS settings...")
        
        # Create recordings folder
        if not os.path.exists(self.recordings_folder):
            os.makedirs(self.recordings_folder)
            print(f"📁 Created recordings folder: {self.recordings_folder}")
        
        # OBS config directory
        obs_config_dir = os.path.expanduser("~/AppData/Roaming/obs-studio")
        
        if os.path.exists(obs_config_dir):
            print(f"📂 OBS config directory: {obs_config_dir}")
            
            # Create a basic profile for recording
            basic_profile = os.path.join(obs_config_dir, "basic", "profiles", "ZoomRecorder")
            os.makedirs(basic_profile, exist_ok=True)
            
            # Create basic.ini
            basic_ini = os.path.join(basic_profile, "basic.ini")
            basic_config = f"""[Basic]
Name=ZoomRecorder

[AdvOut]
RecType=Standard
RecFilePath={self.recordings_folder}
RecFormat=mkv
RecMuxerCustom=matroska,avc1,mp4a
RecQuality=1
RecEncoder=obs_x264
RecAEncoder=ffmpeg_aac
RecTracks=1
RecRescale=1920x1080
RecRateControl=CBR
RecBitrate=2500
RecKeyintSec=2
RecPreset=veryfast
RecProfile=high

[Video]
BaseCX=1920
BaseCY=1080
OutputCX=1920
OutputCY=1080
FPSType=1
FPSCommon=30

[Audio]
SampleRate=44100
ChannelSetup=Stereo
"""
            
            with open(basic_ini, 'w') as f:
                f.write(basic_config)
            
            print("✅ Created OBS recording profile")
            
            # Also create global.ini for WebSocket
            global_ini = os.path.join(obs_config_dir, "global.ini")
            
            if os.path.exists(global_ini):
                # Backup existing
                with open(global_ini, 'r') as f:
                    content = f.read()
                
                # Add WebSocket settings if not present
                if "WebSocket" not in content:
                    content += "\n[WebSocket]\nEnabled=true\nPort=4455\nPassword=6u6vcNXZKyFmE98S\n"
                    with open(global_ini, 'w') as f:
                        f.write(content)
                    print("✅ Updated OBS WebSocket settings")
            else:
                # Create new global.ini
                with open(global_ini, 'w') as f:
                    f.write("[WebSocket]\nEnabled=true\nPort=4455\nPassword=6u6vcNXZKyFmE98S\n")
                print("✅ Created OBS WebSocket config")
        
        return True
    
    def connect_to_obs(self):
        """Connect to OBS WebSocket"""
        print("🔌 Connecting to OBS WebSocket...")
        
        try:
            self.ws = obsws("localhost", self.port, self.password)
            self.ws.connect()
            self.connected = True
            
            # Get version to confirm connection
            version = self.ws.call(requests.GetVersion())
            print(f"✅ Connected to OBS v{version.datain['obsVersion']}")
            return True
            
        except Exception as e:
            print(f"❌ WebSocket connection failed: {e}")
            return False
    
    def setup_recording_automatically(self):
        """Automatically setup recording in OBS"""
        print("🎬 Setting up recording...")
        
        try:
            # Create recordings folder if not exists
            if not os.path.exists(self.recordings_folder):
                os.makedirs(self.recordings_folder)
            
            # Method 1: Set recording folder
            try:
                self.ws.call(requests.SetRecordingFolder({'rec-folder': self.recordings_folder}))
                print(f"✅ Set recording folder: {self.recordings_folder}")
            except:
                pass
            
            # Method 2: Set output settings
            try:
                output_settings = {
                    "path": self.recordings_folder + "\\" + "%CCYY-%MM-%DD_%hh-%mm-%ss.mp4",
                    "format": "mp4",
                    "video_encoder": "obs_x264",
                    "video_encoder_settings": {"bitrate": 2500},
                    "audio_encoder": "ffmpeg_aac",
                    "audio_encoder_settings": {"bitrate": 160}
                }
                self.ws.call(requests.SetOutputSettings(output_settings, "ffmpeg_muxer"))
                print("✅ Configured output settings")
            except:
                pass
            
            # Check/create scene
            self.ensure_scene_exists()
            
            return True
            
        except Exception as e:
            print(f"⚠️ Auto-setup failed: {e}")
            return False
    
    def ensure_scene_exists(self):
        """Make sure OBS has a scene with display capture"""
        try:
            # Get current scenes
            scenes = self.ws.call(requests.GetSceneList())
            
            if not scenes.datain['scenes']:
                print("⚠️ No scenes found, creating one...")
                self.ws.call(requests.CreateScene({'sceneName': 'Zoom Recording'}))
            
            # Get current scene
            current_scene = scenes.datain['main']
            
            # Check if scene has sources
            scene_items = self.ws.call(requests.GetSceneItemList({'sceneName': current_scene}))
            
            if not scene_items.datain['sceneItems']:
                print("⚠️ No sources, trying to add Display Capture...")
                
                # Try to add display capture
                try:
                    source_settings = {
                        "sourceName": "Display Capture 2",
                        "sourceKind": "monitor_capture",
                        "sceneName": current_scene,
                        "sourceSettings": {
                            "monitor": 0,
                            "capture_cursor": True
                        }
                    }
                    self.ws.call(requests.CreateSource(source_settings))
                    print("✅ Added Display Capture source")
                except Exception as e:
                    print(f"⚠️ Could not auto-add source: {e}")
                    print("   Please add a source manually in OBS")
                    return False
            
            else:
                print(f"✅ Scene '{current_scene}' has {len(scene_items.datain['sceneItems'])} source(s)")
            
            return True
            
        except Exception as e:
            print(f"⚠️ Scene setup failed: {e}")
            return False
    
    def start_recording(self):
        """Start OBS recording"""
        print("🔴 Starting recording...")
        
        try:
            # Check current status
            try:
                status = self.ws.call(requests.GetRecordStatus())
                if status.datain.get('outputActive', False):
                    print("⚠️ Already recording!")
                    return True
            except:
                pass
            
            # Start recording
            self.ws.call(requests.StartRecord())
            
            # Verify
            time.sleep(2)
            
            status = self.ws.call(requests.GetRecordStatus())
            if status.datain.get('outputActive', False):
                print("✅ Recording started successfully!")
                print("   Check OBS - should show RED recording indicator")
                return True
            else:
                print("❌ Recording didn't start")
                return False
                
        except Exception as e:
            print(f"❌ Failed to start recording: {e}")
            return False
    
    def stop_recording(self):
        """Stop OBS recording"""
        print("⏹️ Stopping recording...")
        
        try:
            # Stop recording
            self.ws.call(requests.StopRecord())
            time.sleep(3)
            print("✅ Recording stopped")
            self.check_recordings()           
            return True            
        except Exception as e:
            print(f"❌ Failed to stop recording: {e}")
            return False
    
    def check_recordings(self):
        """Check if recordings were created"""
        if os.path.exists(self.recordings_folder):
            files = os.listdir(self.recordings_folder)
            video_files = [f for f in files if f.endswith(('.mp4', '.mkv', '.flv', '.mov', '.avi'))]
            if video_files:
                print(f"\n📁 Found {len(video_files)} recording(s):")
                for file in video_files[:3]:  # Show first 3
                    file_path = os.path.join(self.recordings_folder, file)
                    size = os.path.getsize(file_path) / (1024 * 1024)
                    print(f"   🎬 {file} ({size:.1f} MB)")
            else:
                print(f"\n⚠️ No video files in {self.recordings_folder}")
        else:
            print(f"\n❌ Recordings folder doesn't exist: {self.recordings_folder}")
    
    def run_full_auto(self, duration_seconds=60):
        """Run full automatic recording process"""
        print("="*70)
        print("🤖 AUTO OBS RECORDER - FULLY AUTOMATIC")
        print("="*70)
        
        print(f"\n📁 VSCode Project: {self.project_folder}")
        print(f"📁 Recordings will save to: {self.recordings_folder}")
        
        # Step 1: Start OBS
        print("\n1️⃣ Starting OBS Studio...")
        if not self.start_obs():
            print("\n❌ Failed to start OBS")
            return False
        
        # Wait a bit more for OBS to fully load
        print("⏳ Waiting for OBS to fully initialize...")
        time.sleep(5)
        
        # Step 2: Configure OBS
        print("\n2️⃣ Configuring OBS...")
        self.configure_obs_via_cli()
        
        # Step 3: Connect to OBS
        print("\n3️⃣ Connecting to OBS WebSocket...")
        
        # Try multiple times to connect
        connected = False
        for i in range(5):
            if self.connect_to_obs():
                connected = True
                break
            print(f"   Retrying connection ({i+1}/5)...")
            time.sleep(3)
        
        if not connected:
            print("\n❌ Could not connect to OBS WebSocket")
            print("\n💡 Please manually:")
            print("1. Open OBS Studio")
            print("2. Go to Tools → WebSocket Server Settings")
            print(f"3. Enable WebSocket, Port: {self.port}, Password: {self.password}")
            print("4. Add a Display Capture source")
            print("5. Run this script again")
            return False
        
        # Step 4: Setup recording
        print("\n4️⃣ Setting up recording...")
        if not self.setup_recording_automatically():
            print("⚠️ Auto-setup incomplete, but trying anyway...")
        
        # Step 5: Start recording
        print("\n5️⃣ Starting recording...")
        if not self.start_recording():
            print("\n❌ Failed to start recording automatically")
            print("\n💡 Please manually:")
            print("1. Click 'Start Recording' in OBS")
            print("2. Then run: python interview_bot.py")
            return False
        
        # Step 6: Record for duration
        print(f"\n⏱️ Recording for {duration_seconds} seconds...")
        print("Press Ctrl+C to stop early")
        
        try:
            for i in range(duration_seconds):
                if i % 10 == 0 and i > 0:
                    print(f"   Recording... {i}/{duration_seconds}s")
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n🛑 Early stop requested...")
        
        # Step 7: Stop recording
        print("\n6️⃣ Stopping recording...")
        self.stop_recording()
        
        # Step 8: Disconnect
        print("\n7️⃣ Cleaning up...")
        if self.connected and self.ws:
            self.ws.disconnect()
        
        print("\n✅ Automatic recording complete!")
        return True

def main():
    """Main function"""
    print("🤖 OBS AUTO-RECORDER FOR ZOOM INTERVIEWS")
    print("="*60)
    
    # Get recording duration
    try:
       # minutes = int(input("\nEnter recording duration in minutes (default 10): ") or "10")
        seconds =  60
    except:
        seconds = 600  # 10 minutes
    
    # Create recorder
    recorder = AutoOBSRecorder()
    
    # Run automatic recording
    recorder.run_full_auto(duration_seconds=seconds)
    
    print("\n" + "="*60)
    print("COMPLETE - Check your VSCode project for recordings!")
    print("="*60)

if __name__ == "__main__":
    main()

import os
import cv2
import subprocess
from datetime import datetime

class VideoProcessor:
    def __init__(self, face_swapper_instance):
        """
        Initialize the offline video processor.
        Requires an initialized FaceSwapper instance.
        """
        self.face_swapper = face_swapper_instance
        print("Offline Video Processor Initialized.")

    def process_offline_video(self, input_path, target_face_model, output_dir):
        """
        FR-X.X: Offline Video Upload & Swap.
        Extracts frames, uses FaceSwapper, and restores original audio with ffmpeg.
        Returns the output path of the final MP4.
        """
        if not os.path.exists(output_dir):
            os.makedirs(output_dir, exist_ok=True)
            
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        base_name = os.path.basename(input_path).split('.')[0]
        
        temp_no_audio = os.path.join(output_dir, f"{base_name}_temp_{timestamp}.mp4")
        final_output = os.path.join(output_dir, f"{base_name}_swapped_{timestamp}.mp4")
        
        cap = cv2.VideoCapture(input_path)
        fps = cap.get(cv2.CAP_PROP_FPS)
        width  = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        out = cv2.VideoWriter(temp_no_audio, fourcc, fps, (width, height))
        
        print(f"Starting Offline Face Swap for {base_name} at {fps} FPS...")
        frame_count = 0
        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                break
                
            frame_count += 1
            if frame_count % 30 == 0:
                print(f"Processed {frame_count} frames...")
                
            # Perform face swapping
            swapped = self.face_swapper.process_frame(frame, target_face_model)
            out.write(swapped)
            
        cap.release()
        out.release()
        
        print(f"Face swapping complete. Re-muxing original audio from {input_path}")
        
        # Merge Original Audio with FFMPEG
        cmd = [
            "ffmpeg",
            "-i", temp_no_audio,
            "-i", input_path,
            "-c:v", "copy",
            "-map", "0:v:0",
            "-map", "1:a:0?",
            "-c:a", "aac",
            final_output,
            "-y"
        ]
        
        try:
            subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            print(f"Video finalized successfully: {final_output}")
        except subprocess.CalledProcessError as e:
            print(f"FFMPEG Error: {e}. Outputting temp video without audio.")
            final_output = temp_no_audio
        finally:
            if os.path.exists(temp_no_audio) and final_output != temp_no_audio:
                os.remove(temp_no_audio)
                
        return final_output

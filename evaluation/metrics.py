import numpy as np
from skimage.metrics import structural_similarity as ssim
from skimage.metrics import peak_signal_noise_ratio as psnr
import librosa
import cv2
import time

def calculate_mcd(audio_ref_path, audio_deg_path):
    """
    FR-5.1: Calculate Mel-Cepstral Distortion (MCD) for the generated voice.
    Formula implemented explicitly using librosa's DTW alignment and Euclidean distance.
    """
    print(f"Calculating MCD between {audio_ref_path} and {audio_deg_path}")
    try:
        y_ref, sr_ref = librosa.load(audio_ref_path, sr=None)
        y_deg, sr_deg = librosa.load(audio_deg_path, sr=sr_ref)

        mfcc_ref = librosa.feature.mfcc(y=y_ref, sr=sr_ref, n_mfcc=13)[1:, :]
        mfcc_deg = librosa.feature.mfcc(y=y_deg, sr=sr_ref, n_mfcc=13)[1:, :]

        # Dynamic Time Warping to align sequence elements
        D, wp = librosa.sequence.dtw(mfcc_ref, mfcc_deg)
        
        diff = mfcc_ref[:, wp[:, 0]] - mfcc_deg[:, wp[:, 1]]
        mcd = (10.0 / np.log(10)) * np.sqrt(2.0) * np.mean(np.sqrt(np.sum(diff**2, axis=0)))
        
        print(f"Calculated MCD: {mcd:.2f} dB")
        return mcd
    except Exception as e:
        print(f"Error calculating MCD: {e}")
        return 0.0

def calculate_snr(audio_ref_path, audio_deg_path):
    """
    FR-5.2: Calculate Signal-to-Noise Ratio (SNR) for the generated voice.
    """
    print(f"Calculating SNR between {audio_ref_path} and {audio_deg_path}")
    try:
        y_ref, sr_ref = librosa.load(audio_ref_path, sr=None)
        y_deg, sr_deg = librosa.load(audio_deg_path, sr=sr_ref)

        min_len = min(len(y_ref), len(y_deg))
        y_ref = y_ref[:min_len]
        y_deg = y_deg[:min_len]

        p_signal = np.sum(y_ref ** 2)
        noise = y_ref - y_deg
        p_noise = np.sum(noise ** 2)

        snr = float('inf') if p_noise == 0 else 10 * np.log10(p_signal / p_noise)
        print(f"Calculated SNR: {snr:.2f} dB")
        return snr
    except Exception as e:
        print(f"Error calculating SNR: {e}")
        return 0.0

def calculate_ssim(img_ref_path, img_deg_path):
    """
    FR-5.3: Calculate Structural Similarity Index (SSIM) metric for generated video frame.
    """
    img_ref = cv2.imread(img_ref_path)
    img_deg = cv2.imread(img_deg_path)
    
    if img_ref is None or img_deg is None:
        raise ValueError("Could not load one of the images.")
    
    if img_ref.shape != img_deg.shape:
        img_deg = cv2.resize(img_deg, (img_ref.shape[1], img_ref.shape[0]))
        
    score, diff = ssim(img_ref, img_deg, channel_axis=2, full=True)
    print(f"SSIM Score: {score:.4f}")
    return score

def calculate_psnr(img_ref_path, img_deg_path):
    """
    FR-5.4: Calculate Peak Signal-to-Noise Ratio (PSNR) metric for generated video frame.
    """
    img_ref = cv2.imread(img_ref_path)
    img_deg = cv2.imread(img_deg_path)
    
    if img_ref is None or img_deg is None:
        raise ValueError("Could not load one of the images.")
        
    if img_ref.shape != img_deg.shape:
        img_deg = cv2.resize(img_deg, (img_ref.shape[1], img_ref.shape[0]))
        
    score = psnr(img_ref, img_deg)
    print(f"PSNR Score: {score:.2f} dB")
    return score

def measure_latency(start_time, end_time):
    """
    FR-5.5: Measure the end-to-end latency during real-time simulations.
    Returns latency in milliseconds.
    """
    latency_ms = (end_time - start_time) * 1000.0
    print(f"System Latency: {latency_ms:.2f} ms")
    return latency_ms

if __name__ == '__main__':
    print("Evaluation metrics module ready.")

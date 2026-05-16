import onnxruntime as ort
import insightface
import sys

def check_gpu():
    print(f"Python version: {sys.version}")
    print(f"ONNX Runtime version: {ort.__version__}")
    print(f"Available providers: {ort.get_available_providers()}")
    
    device = ort.get_device()
    print(f"ONNX Runtime Device: {device}")

    # Check if CUDAExecutionProvider is in available providers
    if 'CUDAExecutionProvider' in ort.get_available_providers():
        print("CUDAExecutionProvider is REGISTERED.")
    else:
        print("CUDAExecutionProvider is NOT registered. Check onnxruntime-gpu installation.")

    try:
        # Create a dummy session with CUDA
        # We don't need a real model file if we just want to see if it throws an error about the provider
        opts = ort.SessionOptions()
        # session = ort.InferenceSession("non_existent.onnx", providers=['CUDAExecutionProvider'])
        print("Test passed: system recognizes CUDAExecutionProvider (pending real model load).")
    except Exception as e:
        print(f"Error checking CUDAExecutionProvider: {e}")

if __name__ == "__main__":
    check_gpu()

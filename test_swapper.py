from modules.face_swap import FaceSwapper
import os
import sys

# Ensure the root directory is in sys.path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

def test_init():
    try:
        print("Starting FaceSwapper test...")
        swapper = FaceSwapper()
        
        if swapper.app and hasattr(swapper.app, 'models'):
            print("\n--- FaceAnalysis Models ---")
            for name, model in swapper.app.models.items():
                provider = model.get_provider() if hasattr(model, 'get_provider') else "Unknown"
                print(f"Model: {name}, Provider: {provider}")
        
        print("\nInitialization test completed.")
    except Exception as e:
        print(f"Initialization failed: {e}")

if __name__ == "__main__":
    test_init()

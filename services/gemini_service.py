import os
import sys
import uuid
import base64
import traceback
from typing import Optional
from google import genai
from google.genai import types

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GENERATED_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static", "generated")

os.makedirs(GENERATED_DIR, exist_ok=True)

client = genai.Client(api_key=GEMINI_API_KEY)

IMAGEN_MODELS = [
    "imagen-3.0-generate-002",
    "imagen-3.0-generate-001",
]

GEMINI_IMAGE_MODELS = [
    "gemini-2.0-flash-preview-image-generation",
    "gemini-2.0-flash-exp",
]


def _save_image(image_bytes: bytes, prefix: str) -> str:
    filename = f"{prefix}_{uuid.uuid4().hex[:8]}.png"
    filepath = os.path.join(GENERATED_DIR, filename)
    with open(filepath, "wb") as f:
        f.write(image_bytes)
    return f"/static/generated/{filename}"


def generate_image(prompt: str, prefix: str = "img") -> Optional[str]:
    """Generate an image from a text prompt. Returns the URL path or None on failure."""

    for model in IMAGEN_MODELS:
        try:
            print(f"[IMG] Trying Imagen model: {model}", file=sys.stderr)
            response = client.models.generate_images(
                model=model,
                prompt=prompt,
                config=types.GenerateImagesConfig(
                    number_of_images=1,
                    aspect_ratio="1:1",
                    safety_filter_level="BLOCK_ONLY_HIGH",
                ),
            )
            if response.generated_images and len(response.generated_images) > 0:
                image_data = response.generated_images[0].image.image_bytes
                url = _save_image(image_data, prefix)
                print(f"[IMG] Success with {model}: {url}", file=sys.stderr)
                return url
            else:
                print(f"[IMG] {model} returned no images", file=sys.stderr)
        except Exception as e:
            print(f"[IMG] {model} failed: {e}", file=sys.stderr)

    for model in GEMINI_IMAGE_MODELS:
        try:
            print(f"[IMG] Trying Gemini native model: {model}", file=sys.stderr)
            response = client.models.generate_content(
                model=model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_modalities=["TEXT", "IMAGE"]
                ),
            )

            if response.candidates:
                for part in response.candidates[0].content.parts:
                    if hasattr(part, "inline_data") and part.inline_data and hasattr(part.inline_data, "mime_type"):
                        if part.inline_data.mime_type and part.inline_data.mime_type.startswith("image/"):
                            image_data = part.inline_data.data
                            if isinstance(image_data, str):
                                image_data = base64.b64decode(image_data)
                            url = _save_image(image_data, prefix)
                            print(f"[IMG] Success with {model}: {url}", file=sys.stderr)
                            return url
            print(f"[IMG] {model} returned no image parts", file=sys.stderr)
        except Exception as e:
            print(f"[IMG] {model} failed: {e}", file=sys.stderr)
            traceback.print_exc(file=sys.stderr)

    print("[IMG] All image generation methods failed", file=sys.stderr)
    return None


def generate_images_for_questions(questions: dict) -> dict:
    """Generate images for map_based and political_cartoon questions. Mutates and returns questions."""
    for i, q in enumerate(questions.get("map_based", [])):
        prompt = q.get("image_prompt", "")
        if prompt:
            map_prompt = (
                "Create a clean, labeled educational map illustration. "
                "Use clear labels with letters A, B, C, D for key locations. "
                "Style: textbook-quality, simple colors, clear borders and labels. "
                f"Details: {prompt}"
            )
            print(f"[IMG] Generating map {i+1}/3...", file=sys.stderr)
            url = generate_image(map_prompt, prefix="map")
            q["image_url"] = url

    for i, q in enumerate(questions.get("political_cartoon", [])):
        prompt = q.get("image_prompt", "")
        if prompt:
            cartoon_prompt = (
                "Create an educational political cartoon or historical illustration. "
                "Style: editorial cartoon with clear symbolic elements and labels. "
                "Make it suitable for a history classroom. "
                f"Details: {prompt}"
            )
            print(f"[IMG] Generating cartoon {i+1}/3...", file=sys.stderr)
            url = generate_image(cartoon_prompt, prefix="cartoon")
            q["image_url"] = url

    return questions

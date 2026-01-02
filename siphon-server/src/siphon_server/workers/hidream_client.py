import os
import argparse
import logging
import httpx
from pathlib import Path
from jinja2 import Template

NAS_DIR = os.getenv("NAS", "/tmp")
IMAGES_DIR_PATH = Path(NAS_DIR).resolve() / "generated_images"
IMAGES_DIR_PATH.mkdir(parents=True, exist_ok=True)

logger = logging.getLogger(__name__)
HIDREAM_SERVICE_URL = "http://localhost:8003"

TRMNL_PROMPT = """
SYSTEM PROMPT FOR E-INK–OPTIMIZED IMAGE GENERATION
... [Same rules as your previous files] ...
Now here is the user prompt:
<PROMPT>
{{ prompt }}
</PROMPT>
"""


def generate_hidream(
    prompt: str,
    output_file: Path,
    steps: int = 28,
    guidance: float = 0.0,
    seed: int = 42,
) -> Path:
    payload = {"prompt": prompt, "steps": steps, "guidance": guidance, "seed": seed}

    try:
        with httpx.Client(timeout=120.0) as client:
            response = client.post(f"{HIDREAM_SERVICE_URL}/generate", json=payload)
            if response.status_code != 200:
                raise RuntimeError(f"HiDream error: {response.text}")

            with open(output_file, "wb") as f:
                f.write(response.content)
            return output_file
    except Exception as e:
        raise RuntimeError(f"Generation failed: {e}")


def stem_prompt(prompt: str) -> str:
    import re

    return re.sub(r"[^a-z0-9_]", "", prompt.lower().replace(" ", "_"))[:50]


def generate_raw_hidream(prompt: str) -> Path:
    return generate_hidream(prompt, IMAGES_DIR_PATH / f"hd_{stem_prompt(prompt)}.png")


def generate_trmnl_hidream(prompt: str) -> Path:
    full_prompt = str(Template(TRMNL_PROMPT).render(prompt=prompt))
    return generate_hidream(
        full_prompt, IMAGES_DIR_PATH / f"hd_trmnl_{stem_prompt(prompt)}.png"
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("prompt")
    parser.add_argument("--trmnl", "-t", action="store_true")
    args = parser.parse_args()

    path = (
        generate_trmnl_hidream(args.prompt)
        if args.trmnl
        else generate_raw_hidream(args.prompt)
    )
    print(f"Generated at: {path}")


# if __name__ == "__main__":
#     main()

if __name__ == "__main__":
    prompt = (
        "A female barbarian fighting a gnoll in a dark forest, high detail, fantasy art"
    )
    prompts = """
 Grimdark Super-Soldier: A towering genetically enhanced warrior in ancient powered armor, scarred ceramite plates covered in purity seals and gothic engravings, glowing red eye lenses, standing in a rain-soaked battlefield of ash and fire, cathedral ruins in the background, baroque sci-fi aesthetic, extreme detail, dark high-contrast lighting, cinematic composition, brutal and oppressive mood
Gothic Hive City: A colossal hive city stretching into polluted clouds, impossibly tall gothic spires, flying gunships between towers, endless layers of industrial machinery and cathedrals fused together, dim orange smog, tiny human figures for scale, dystopian sci-fi, brutalist gothic architecture, ultra-wide shot, grimdark atmosphere
Chaos Warped Warrior: A corrupted power-armored warrior fused with daemonic flesh, cracked armor leaking glowing warp energy, horns and twisted metal growing from the body, infernal symbols carved into armor, hellish battlefield with swirling red and purple energy, cosmic horror sci-fi, painterly but hyper-detailed, violent and unstable composition
Tech-Priest of a Machine Cult: A robed techno-priest covered in cables, bionic limbs, and mechanical implants, face partially replaced with brass machinery, glowing green data-runes floating in the air, standing inside a vast industrial cathedral full of pipes and cogwheels, incense smoke and cold lighting, ritualistic sci-fi aesthetic, extreme detail
Alien Bio-Horror Swarm: A massive alien creature leading a swarm of biomechanical monsters, chitinous armor, exposed sinew, clawed limbs and fanged maws, organic weapons grown from flesh, ruined battlefield overrun by alien forms, dark alien color palette, cosmic horror sci-fi, dynamic motion, overwhelming sense of scale
Last Stand Battlefield: A small group of armored soldiers making a desperate last stand against overwhelming enemies, burning tanks and shattered banners, artillery fire lighting the sky, dramatic silhouettes, smoke and embers everywhere, heroic but hopeless tone, cinematic framing, grimdark war sci-fi realism
Emperor-Like Iconography (Abstract): A massive golden throne-like structure surrounded by candles, skull motifs, and towering gothic arches, radiant yet oppressive light, religious sci-fi symbolism, sense of ancient decay and divine authority, symmetrical composition, dark fantasy sci-fi fusion
Void War Scene: Gigantic cathedral-shaped warships battling in deep space, broadsides firing incandescent energy beams, debris fields and burning wreckage, stars obscured by smoke and fire, gothic sci-fi naval warfare, epic scale, high contrast lighting, painterly cinematic style""".strip().splitlines()
    from random import choice

    path = generate_trmnl_hidream(choice(prompts))
    print(f"Generated image at: {path}")

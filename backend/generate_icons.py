import os
from PIL import Image, ImageDraw


def create_icon(filename, color, text_symbol=None, shape='circle'):
    size = (64, 64)
    img = Image.new('RGBA', size, (255, 255, 255, 0))
    draw = ImageDraw.Draw(img)

    padding = 8
    bbox = (padding, padding, size[0] - padding, size[1] - padding)

    # Draw background/shape
    if shape == 'circle':
        draw.ellipse(bbox, outline=color, width=4)
    elif shape == 'filled_circle':
        draw.ellipse(bbox, fill=color)
    elif shape == 'square':
        draw.rectangle(bbox, outline=color, width=4)
    elif shape == 'filled_square':
        draw.rectangle(bbox, fill=color)

    # Draw symbol (simplified)
    center = (size[0] // 2, size[1] // 2)
    if text_symbol:
        # Basic representation of symbol
        draw.text((center[0]-10, center[1]-10), text_symbol, fill=color if 'filled' not in shape else 'white')

    # Ensure directory exists
    output_dir = os.path.join(os.path.dirname(__file__), '../frontend/wechat_mini_program/images')
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    output_path = os.path.join(output_dir, filename)
    img.save(output_path, 'PNG')
    print(f"Created {output_path}")


# Colors
gray = "#7A7E83"
blue = "#007AFF"

# Generate icons
# Home
create_icon('home.png', gray, 'H', 'circle')
create_icon('home-active.png', blue, 'H', 'filled_circle')

# Health Records (Folder/Chat)
create_icon('records.png', gray, 'R', 'square')
create_icon('records-active.png', blue, 'R', 'filled_square')

# Medication (Pill)
create_icon('medication.png', gray, 'M', 'circle')
create_icon('medication-active.png', blue, 'M', 'filled_circle')

# Summary (Doc)
create_icon('summary.png', gray, 'S', 'square')
create_icon('summary-active.png', blue, 'S', 'filled_square')

# Profile (User)
create_icon('profile.png', gray, 'P', 'circle')
create_icon('profile-active.png', blue, 'P', 'filled_circle')

# Chat (AI)
create_icon('chat.png', gray, 'AI', 'circle')
create_icon('chat-active.png', blue, 'AI', 'filled_circle')

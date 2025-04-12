import io
from flask import Flask, send_file, request, Response
import os
from PIL import Image, ImageDraw, ImageFont
from deep_translator import GoogleTranslator
import os, easyocr
import numpy as np

app = Flask(__name__)

UPLOAD_FOLDER = "input"

DOWNLOAD_FOLDER = "static"

reader = easyocr.Reader(["en", "az"], model_storage_directory = 'model')

translator = GoogleTranslator(source="en", target="az")

def perform_ocr(image_path, reader):
    result = reader.readtext(image_path, width_ths = 0.8,  decoder = 'wordbeamsearch')

    extracted_text_boxes = [(entry[0], entry[1]) for entry in result if entry[2] > 0.4]

    return extracted_text_boxes


def get_font(image, text, width, height):

    font_size = None
    
    font_path = "./fonts/NotoSans-Regular.ttf"
    
    font_size = 36
    
    font = ImageFont.truetype(font_path, font_size)
    
    box = None
    
    x = 0
    
    y = 0

    draw = ImageDraw.Draw(image)

    for size in range(1, 500):
        new_font = ImageFont.truetype(font_path, size)

        new_box = draw.textbbox((0, 0), text, font=new_font)

        new_w = new_box[2] - new_box[0]
        
        new_h = new_box[3] - new_box[1]

        if new_w > width or new_h > height:
            break

        font_size = size
        
        font = new_font
        
        box = new_box
        
        w = new_w
        
        h = new_h

        x = (width - w) // 2 - box[0]
        
        y = (height - h) // 2 - box[1]

    return font, x, y


def add_discoloration(color, strength):
    color = color or (0, 0, 0)
    
    if len(color) == 4:
        r, g, b, a = color
    else:
        r, g, b = color
    
    r = max(0, min(255, r + strength))
    
    g = max(0, min(255, g + strength))
    
    b = max(0, min(255, b + strength))
    
    if r == 255 and g == 255 and b == 255:
        r, g, b = 245, 245, 245

    return (r, g, b)


def get_background_color(image, x_min, y_min, x_max, y_max):
    margin = 10

    edge_region = image.crop(
        (
            max(x_min - margin, 0),
            max(y_min - margin, 0),
            min(x_max + margin, image.width),
            min(y_max + margin, image.height),
        )
    )

    edge_colors = edge_region.getcolors(edge_region.size[0] * edge_region.size[1])

    background_color = max(edge_colors, key=lambda x: x[0])[1]
    
    background_color = add_discoloration(background_color, 40)

    return background_color


def get_text_fill_color(background_color):
    luminance = (
        0.299 * background_color[0]
        + 0.587 * background_color[1]
        + 0.114 * background_color[2]
    ) / 255

    if luminance > 0.5:
        return "black"
    else:
        return "white"


def replace_text_with_translation(image, translated_texts, text_boxes):
    draw = ImageDraw.Draw(image)

    font = ImageFont.load_default()

    for text_box, translated in zip(text_boxes, translated_texts):
        if translated is None:
            continue

        x_min, y_min = text_box[0][0][0], text_box[0][0][1]

        x_max, y_max = text_box[0][0][0], text_box[0][0][1]

        for coordinate in text_box[0]:

            x, y = coordinate

            if x < x_min:
                x_min = x
            elif x > x_max:
                x_max = x
            if y < y_min:
                y_min = y
            elif y > y_max:
                y_max = y

        background_color = get_background_color(image, x_min, y_min, x_max, y_max)

        draw.rectangle(((x_min, y_min), (x_max, y_max)), fill=background_color)

        font, x, y = get_font(image, translated, x_max - x_min, y_max - y_min)

        draw.text(
            (x_min + x, y_min + y),
            translated,
            fill=get_text_fill_color(background_color),
            font=font,
        )

    return image

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

@app.route('/upload', methods=['POST'])
def upload_image():
    if 'file' not in request.files:
        return "No file uploaded", 400

    file = request.files['file']

    image = Image.open(file.stream)

    # new_size = (240, 240)

    # image = image.resize(new_size, Image.LANCZOS)

    reader = easyocr.Reader(["en", "az"], model_storage_directory='model')

    translator = GoogleTranslator(source="en", target="az")

    img_np = np.array(image)

    extracted_text_boxes = perform_ocr(img_np, reader)

    translated_texts = []
    for text_box, text in extracted_text_boxes:
        translated_texts.append(translator.translate(text))

    image = replace_text_with_translation(image, translated_texts, extracted_text_boxes)

    image = image.convert('RGB')

    img_byte_arr = io.BytesIO()

    image.save(img_byte_arr, format='BMP')

    img_byte_arr.seek(0)

    return send_file(img_byte_arr, mimetype='image/bmp')

@app.route('/')
def index():
	return 'This is image translator web server'

if __name__ == '__main__':
    from waitress import serve
    import os
    port = int(os.environ.get("PORT", 10000))
    serve(app, host="0.0.0.0", port=port)

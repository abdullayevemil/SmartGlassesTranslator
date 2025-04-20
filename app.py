from flask import Flask, request, jsonify
import os
from PIL import Image
from deep_translator import GoogleTranslator
import os, easyocr
import numpy as np
import requests
import re
# from pyngrok import ngrok
from waitress import serve
import logging
logging.basicConfig(filename='logfile.txt', level=logging.INFO)

def strip_html(text):
    return re.sub('<[^<]+?>', '', text)

app = Flask(__name__)

reader = easyocr.Reader(["en", "az"], model_storage_directory = 'model')

translator = GoogleTranslator(source="en", target="az")

GOOGLE_MAPS_API_KEY = 'AIzaSyDfXX5PPgoXWGATdowAcuWzQcIFXaCoJaU'

current_location = {"lat": None, "lng": None}
destination_address = None
last_direction_text = ""

def perform_ocr(image_path, reader):
    result = reader.readtext(image_path, width_ths = 0.8,  decoder = 'wordbeamsearch')

    extracted_text_boxes = [(entry[0], entry[1]) for entry in result if entry[2] > 0.4]

    return extracted_text_boxes

def get_coordinates(translated_texts, text_boxes, width):
    result = []
    
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

        result.append(int(x_min + x) * 64 // width)
        
        result.append(int(y_min + y) * 64 // width)

    return result

@app.route('/upload', methods=['POST'])
def upload_image():
    if 'file' not in request.files:
        return "No file uploaded", 400

    file = request.files['file']
    
    logging.info("File received: %s", file.filename)

    image = Image.open(file.stream)

    logging.info("Image opened: %s", file.filename)

    width, height = image.size

    width, height = image.size
    
    logging.info("Image size: %s x %s", width, height)

    new_height = width / 2 

    left = 0
    
    top = (height - new_height) / 2
    
    right = width
    
    bottom = top + new_height

    image = image.crop((left, top, right, bottom))
    
    img_np = np.array(image)

    extracted_text_boxes = perform_ocr(img_np, reader)
    
    logging.info("Extracted text boxes: %s", extracted_text_boxes)

    translated_texts = []
    for text_box, text in extracted_text_boxes:
        translated_texts.append(translator.translate(text))
        
    coordinates = get_coordinates(translated_texts, extracted_text_boxes, width)
    
    logging.info("Coordinates: %s", coordinates)
    
    logging.info("Translated texts: %s", translated_texts)
    
    return jsonify({
        "coordinates": coordinates,
        "translated_texts": translated_texts
    })

@app.route('/')
def index():
	return 'This is image translator web server'

@app.route('/set-destination', methods=['POST'])
def set_destination():
    global destination_address
    data = request.get_json()
    destination_address = data.get('destination')
    return jsonify({"status": "destination set", "destination": destination_address})

@app.route('/update-location', methods=['POST'])
def update_location():
    global current_location, last_direction_text

    data = request.get_json()
    lat = data.get('lat')
    lng = data.get('lng')

    current_location = {"lat": lat, "lng": lng}

    if not destination_address:
        return jsonify({"error": "Destination not set yet"}), 400

    # Call Google Maps Directions API
    directions_url = (
        f"https://maps.googleapis.com/maps/api/directions/json"
        f"?origin={lat},{lng}"
        f"&destination={destination_address}"
        f"&key={GOOGLE_MAPS_API_KEY}"
    )

    res = requests.get(directions_url)
    directions = res.json()

    if directions["status"] != "OK":
        return jsonify({"error": "Failed to get directions", "details": directions}), 500

    steps = directions["routes"][0]["legs"][0]["steps"]
    if steps:
        next_step = steps[0]["html_instructions"]
        distance = steps[0]["distance"]["text"]
        last_direction_text = f"{strip_html(next_step)} in {distance}"
    else:
        last_direction_text = "You have arrived."

    return jsonify({"status": "location updated", "next_direction": last_direction_text})

@app.route('/route/next-step', methods=['GET'])
def get_next_step():
    return jsonify({"direction": last_direction_text})

if __name__ == '__main__':
    # public_url = ngrok.connect(10000)
    # print("Public URL:", public_url)
    port = int(os.environ.get("PORT", 10000))
    serve(app, host="0.0.0.0", port=port, threads=4)

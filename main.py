from flask import Flask, request, jsonify
import requests
from PIL import Image
import numpy as np
import io
import math

app = Flask(__name__)
NEXTZEN_API_KEY = 'N-y9kIrESbaIApeIkLrXCA'  # Replace with your actual API key

@app.route('/terrain', methods=['GET'])
def get_terrain():
    zoom = request.args.get('zoom')
    tilex = request.args.get('tilex')
    tiley = request.args.get('tiley')
    resolution = request.args.get('resolution')
    type_ = request.args.get('type')

    if not all([zoom, tilex, tiley, resolution, type_]):
        return "Missing parameters: zoom, tilex, tiley, resolution, type", 400

    try:
        resize_dim = int(resolution)
        if resize_dim <= 0:
            return "Invalid resolution parameter: must be a positive integer", 400

        bbox = tile_to_bbox(int(tilex), int(tiley), int(zoom))
        overpass_data = get_overpass_data(bbox)
        nextzen_data = get_nextzen_data(zoom, tilex, tiley)

        if type_ == "Flat":
            return jsonify({
                "overpassData": overpass_data,
                "nextzenData": nextzen_data
            })

        if type_ == "Terrain":
            terrain_url = f"https://api.mapbox.com/v4/mapbox.terrain-rgb/{zoom}/{tilex}/{tiley}.pngraw?access_token=pk.eyJ1IjoiYWVyb3gyMDI0IiwiYSI6ImNscTFpM3RjcDA5dmQydnJ5dWduc3phNHIifQ.CL1jxgUxLJtOaI_JF8PIhQ"
            satellite_url = f"https://api.mapbox.com/v4/mapbox.satellite/{zoom}/{tilex}/{tiley}.pngraw?access_token=pk.eyJ1IjoiYWVyb3gyMDI0IiwiYSI6ImNscTFpM3RjcDA5dmQydnJ5dWduc3phNHIifQ.CL1jxgUxLJtOaI_JF8PIhQ"
            
            terrain_response = requests.get(terrain_url)
            satellite_response = requests.get(satellite_url)

            if not terrain_response.ok or not satellite_response.ok:
                return "Error fetching terrain or satellite images", 500

            terrain_height_data = get_height_data(terrain_response.content, resize_dim)
            satellite_hex_data = get_hex_data(satellite_response.content, resize_dim)

            return jsonify({
                "terrainHeightData": terrain_height_data,
                "satelliteHexData": satellite_hex_data,
                "nextzenData": nextzen_data,
                "overpassData": overpass_data
            })

        return "Invalid type parameter. Only 'Flat' and 'Terrain' are accepted.", 400

    except Exception as e:
        print(e)
        return "Error processing images or fetching data", 500

def get_nextzen_data(zoom, tilex, tiley):
    nextzen_url = f"https://tile.nextzen.org/tilezen/vector/v1/all/{zoom}/{tilex}/{tiley}.json?api_key={NEXTZEN_API_KEY}"
    response = requests.get(nextzen_url)
    response.raise_for_status()
    return response.json()

def get_overpass_data(bbox):
    overpass_query = f"""
        [out:json];
        (
          node["aeroway"]({bbox});
          way["aeroway"]({bbox});
          relation["aeroway"]({bbox});
          node["landuse"="grass"]({bbox});
          way["landuse"="grass"]({bbox});
          relation["landuse"="grass"]({bbox});
          node["natural"="water"]({bbox});
          way["natural"="water"]({bbox});
          relation["natural"="water"]({bbox});
          node["natural"="tree"]({bbox});
          way["natural"="tree"]({bbox});
          relation["natural"="tree"]({bbox});
        );
        out body;
        >;
        out skel qt;
    """
    response = requests.post('http://overpass-api.de/api/interpreter', data={'data': overpass_query})
    response.raise_for_status()
    return response.json()

def tile_to_bbox(tilex, tiley, zoom):
    lon_min = tilex / (2 ** zoom) * 360 - 180
    lon_max = (tilex + 1) / (2 ** zoom) * 360 - 180
    lat_min = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * (tiley + 1) / (2 ** zoom)))))
    lat_max = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * tiley / (2 ** zoom)))))
    return f"{lat_min},{lon_min},{lat_max},{lon_max}"

def get_height_data(image_content, resize_dim):
    img = Image.open(io.BytesIO(image_content)).resize((resize_dim, resize_dim))
    pixels = np.array(img)
    height_data = [[-10000 + ((r * 256 * 256 + g * 256 + b) * 0.1) for r, g, b, _ in row] for row in pixels]
    return height_data

def get_hex_data(image_content, resize_dim):
    img = Image.open(io.BytesIO(image_content)).resize((resize_dim, resize_dim))
    pixels = np.array(img)
    hex_data = [[rgb_to_hex(r, g, b) for r, g, b, _ in row] for row in pixels]
    return hex_data

def rgb_to_hex(r, g, b):
    return f"#{r:02x}{g:02x}{b:02x}"

if __name__ == '__main__':
    app.run(debug=True, host="0.0.0.0")

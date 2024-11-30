from flask import Flask, request, jsonify
import requests
from PIL import Image
import numpy as np
from io import BytesIO
import json

app = Flask(__name__)

# Constants
TERRARIUM_URL = "https://tile.nextzen.org/tilezen/terrain/v1/256/terrarium/{zoom}/{x}/{z}.png?api_key=Wf4VKN0qQIebdQBFqlNWEQ"
SATELLITE_URL = "https://2.aerial.maps.api.here.com/maptile/2.1/maptile/newest/satellite.day/{zoom}/{x}/{z}/512/png?app_id=pcXBZARHILwXlCihx8d6&token=dzJKV7oQT-zs-vRT_KqiLA&lg=ENG"
OVERPASS_API = "https://overpass-api.de/api/interpreter"
NEXTZEN_API = "https://tile.nextzen.org/"

def fetch_and_resize_image(url, x, z, zoom, res):
    # Fetch the image from the URL
    response = requests.get(url.format(zoom=zoom, x=x, z=z))
    response.raise_for_status()
    
    # Open the image and resize
    image = Image.open(BytesIO(response.content))
    return image.resize((res, res))

def decode_terrarium_elevation(terrarium_img):
    # Decode the Terrarium image into elevation
    pixels = np.array(terrarium_img)
    elevations = (pixels[:, :, 0] * 256 + pixels[:, :, 1] + pixels[:, :, 2] / 256) - 32768
    return elevations

def satellite_to_hex(satellite_img):
    # Convert the satellite image pixels to HEX
    pixels = np.array(satellite_img)
    hex_colors = np.apply_along_axis(lambda rgb: "#{:02x}{:02x}{:02x}".format(*rgb), 2, pixels)
    return hex_colors

def fetch_nextzen_data(zoom, x, z):
    # Fetch raw data from Nextzen API
    url = f"{NEXTZEN_API}tilezen/terrain/v1/256/{zoom}/{x}/{z}.mvt?api_key=Wf4VKN0qQIebdQBFqlNWEQ"
    response = requests.get(url)
    response.raise_for_status()
    return response.content

def fetch_overpass_data(bbox):
    # Fetch Overpass data
    query = f"""
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
    response = requests.post(OVERPASS_API, data={"data": query})
    response.raise_for_status()
    return response.json()

def calculate_bbox(coordsx, coordsz, zoom):
    # Calculate bounding box for Overpass query based on tile coordinates
    n = 2 ** zoom
    lon_min = coordsx / n * 360.0 - 180.0
    lon_max = (coordsx + 1) / n * 360.0 - 180.0
    lat_min = np.degrees(np.arctan(np.sinh(np.pi * (1 - 2 * coordsz / n))))
    lat_max = np.degrees(np.arctan(np.sinh(np.pi * (1 - 2 * (coordsz + 1) / n))))
    return f"{lat_min},{lon_min},{lat_max},{lon_max}"

@app.route('/terrain', methods=['GET'])
def get_terrain():
    try:
        # Get parameters from URL
        coordsx = int(request.args.get('coordsx'))
        coordsz = int(request.args.get('coordsz'))
        res = int(request.args.get('res'))
        zoom = int(request.args.get('zoom'))

        # Fetch and process Terrarium image
        terrarium_img = fetch_and_resize_image(TERRARIUM_URL, coordsx, coordsz, zoom, res)
        elevations = decode_terrarium_elevation(terrarium_img)

        # Fetch and process Satellite image
        satellite_img = fetch_and_resize_image(SATELLITE_URL, coordsx, coordsz, zoom, res)
        hex_colors = satellite_to_hex(satellite_img)

        # Fetch Nextzen data
        nextzen_data = fetch_nextzen_data(zoom, coordsx, coordsz)

        # Fetch Overpass data
        bbox = calculate_bbox(coordsx, coordsz, zoom)
        overpass_data = fetch_overpass_data(bbox)

        # Return processed data as JSON
        return jsonify({
            "elevations": elevations.tolist(),  # Convert numpy array to list
            "hex_colors": hex_colors.tolist(),  # Convert numpy array to list
            "nextzen_data": nextzen_data.decode('utf-8'),  # Return raw Nextzen data as string
            "overpass_data": overpass_data  # Overpass data is already a JSON object
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)

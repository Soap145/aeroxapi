from flask import Flask, request, jsonify
import requests
from PIL import Image
import numpy as np
from shapely.geometry import Polygon
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
                "nextzenData": nextzen_data,
                "flatPolygons": get_flat_polygons(nextzen_data)
            })

        if type_ == "Terrain":
            terrain_url = f"https://tile.nextzen.org/tilezen/terrain/v1/256/terrarium/{zoom}/{tilex}/{tiley}.png?api_key=Wf4VKN0qQIebdQBFqlNWEQ"
            satellite_url = f"https://2.aerial.maps.api.here.com/maptile/2.1/maptile/newest/satellite.day/{zoom}/{tilex}/{tiley}/256/png?app_id=pcXBZARHILwXlCihx8d6&token=dzJKV7oQT-zs-vRT_KqiLA&lg=ENG"
            
            terrain_response = requests.get(terrain_url)
            satellite_response = requests.get(satellite_url)

            if not terrain_response.ok or not satellite_response.ok:
                return  terrain_response, 500# "Error fetching terrain or satellite images", 500

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
        return  "Error processing images or fetching data", 500

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
    try:
        # Open the image, convert to RGB, and resize
        img = Image.open(io.BytesIO(image_content)).convert("RGB").resize((resize_dim, resize_dim))
        pixels = np.array(img)
        
        # Debugging outputs
        print("Height Data - Pixel array shape:", pixels.shape)
        print("Height Data - Pixel dtype:", pixels.dtype)
        
        # Validate shape and type
        if pixels.ndim != 3 or pixels.shape[2] != 3:
            raise ValueError("Unexpected image format. Ensure the image is RGB.")
        if pixels.dtype != np.uint8:
            raise ValueError("Pixel values must be uint8.")
        
        # Process height data
        height_data = [
            [(np.uint16(r) * 256 + np.uint16(g) + np.uint16(b) / 256) - 32768 for r, g, b in row]
            for row in pixels
        ]

        return height_data
    
    except Exception as e:
        print("Error in get_height_data:", e)
        raise

def get_hex_data(image_content, resize_dim):
    try:
        # Open the image, convert to RGB, and resize
        img = Image.open(io.BytesIO(image_content)).convert("RGB").resize((resize_dim, resize_dim))
        pixels = np.array(img)
        
        # Debugging outputs
        print("Hex Data - Pixel array shape:", pixels.shape)
        print("Hex Data - Pixel dtype:", pixels.dtype)
        
        # Validate shape and type
        if pixels.ndim != 3 or pixels.shape[2] != 3:
            raise ValueError("Unexpected image format. Ensure the image is RGB.")
        if pixels.dtype != np.uint8:
            raise ValueError("Pixel values must be uint8.")
        
        # Convert to hex
        hex_data = [[rgb_to_hex(r, g, b) for r, g, b in row] for row in pixels]
        return hex_data
    
    except Exception as e:
        print("Error in get_hex_data:", e)
        raise


def get_flat_polygons(nextzen):
    water_polys = []
    earth_polys = []
    if "water" in nextzen:
        for water in nextzen["water"]["features"]:
            geometry = water["geometry"]
            if geometry["type"] == "Polygon":
                coords = [(c[1], c[0]) for c in geometry["coordinates"][0]]
                water_polys.append(Polygon(coords))
            elif geometry["type"] == "MultiPolygon":
                for uclist in geometry["coordinates"]:
                    for clist in uclist:
                        coords = [(c[1], c[0]) for c in clist]
                        water_polys.append(Polygon(coords))

    if "earth" in nextzen:
        for earth in nextzen["earth"]["features"]:
            geometry = earth["geometry"]
            if geometry["type"] == "Polygon":
                poly = Polygon([(c[1], c[0]) for c in geometry["coordinates"][0]])
                for water in water_polys:
                    poly = poly.difference(water)

                polys = poly.geoms if poly.geom_type == "MultiPolygon" else [poly]
                for p in polys:
                    earth_polys.append(list(p.exterior.coords))
            elif geometry["type"] == "MultiPolygon":
                for uclist in geometry["coordinates"]:
                    for clist in uclist:
                        poly = Polygon([(c[1], c[0]) for c in clist])
                        for water in water_polys:
                            poly = poly.difference(water)

                        polys = poly.geoms if poly.geom_type in ("MultiPolygon", "GeometryCollection") else [poly]
                        for p in polys:
                            earth_polys.append(list(p.exterior.coords))
    return earth_polys

def rgb_to_hex(r, g, b):
    return f"#{r:02x}{g:02x}{b:02x}"

if __name__ == '__main__':
    app.run(debug=True, host="0.0.0.0")

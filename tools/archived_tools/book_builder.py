import os
import json
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import landscape
from reportlab.lib.units import mm
from PIL import Image

def create_index_file(params):
    filename = params.get("filename", "book_index.json")
    with open(filename, 'w') as f:
        json.dump({"pages": [], "cover": {}}, f, indent=2)
    return {"status": "success", "message": f"Index file '{filename}' created."}

def add_images_to_index(params):
    image_dir = params["image_dir"]
    filename = params.get("filename", "book_index.json")
    prefix = params.get("entry_key_prefix", "page")

    images = sorted([f for f in os.listdir(image_dir) if f.lower().endswith(('.png', '.jpg', '.jpeg'))])

    if not os.path.exists(filename):
        return {"status": "error", "message": f"Index file '{filename}' not found."}

    with open(filename, 'r') as f:
        data = json.load(f)

    for img in images:
        full_path = os.path.join(image_dir, img)
        data["pages"].append(full_path)

    with open(filename, 'w') as f:
        json.dump(data, f, indent=2)

    return {"status": "success", "message": f"Added {len(images)} images to index."}

def compile_book_from_index(params):
    index_file = params.get("filename", "book_index.json")
    output_pdf = params.get("output_pdf", "output_book.pdf")

    if not os.path.exists(index_file):
        return {"status": "error", "message": f"Index file '{index_file}' not found."}

    with open(index_file, 'r') as f:
        data = json.load(f)

    pages = data.get("pages", [])
    cover = data.get("cover", {})

    if len(pages) % 2 != 0:
        return {"status": "error", "message": "Page count must be even."}

    page_width = 297 * mm
    page_height = 210 * mm

    c = canvas.Canvas(output_pdf, pagesize=landscape((page_width, page_height)))

    def draw_image(path):
        if not os.path.exists(path):
            return
        try:
            img = Image.open(path)
            img_width, img_height = img.size
            aspect = img_width / img_height
            target_width = page_width
            target_height = page_height

            if aspect > target_width / target_height:
                scaled_width = target_width
                scaled_height = target_width / aspect
            else:
                scaled_height = target_height
                scaled_width = target_height * aspect

            x = (page_width - scaled_width) / 2
            y = (page_height - scaled_height) / 2
            c.drawImage(path, x, y, width=scaled_width, height=scaled_height)
        except Exception as e:
            pass

    if "front" in cover:
        draw_image(cover["front"])
        c.showPage()

    for page in pages:
        draw_image(page)
        c.showPage()

    if "back" in cover:
        draw_image(cover["back"])
        c.showPage()

    c.save()
    return {"status": "success", "message": f"Book compiled to '{output_pdf}'"}

def update_cover_image(params):
    filename = params.get("filename", "book_index.json")
    front = params.get("front")
    back = params.get("back")

    if not os.path.exists(filename):
        return {"status": "error", "message": f"Index file '{filename}' not found."}

    with open(filename, 'r') as f:
        data = json.load(f)

    if front:
        data.setdefault("cover", {})["front"] = front
    if back:
        data.setdefault("cover", {})["back"] = back

    with open(filename, 'w') as f:
        json.dump(data, f, indent=2)

    return {"status": "success", "message": "Cover image paths updated."}

def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('action')
    parser.add_argument('--params')
    args = parser.parse_args()
    params = json.loads(args.params) if args.params else {}

    if args.action == 'create_index_file':
        result = create_index_file(params)
    elif args.action == 'add_images_to_index':
        result = add_images_to_index(params)
    elif args.action == 'compile_book_from_index':
        result = compile_book_from_index(params)
    elif args.action == 'update_cover_image':
        result = update_cover_image(params)
    else:
        result = {"status": "error", "message": f"Unknown action {args.action}"}

    print(json.dumps(result, indent=2))

if __name__ == '__main__':
    main()
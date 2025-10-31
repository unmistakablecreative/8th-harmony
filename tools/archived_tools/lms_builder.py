import os
import json
import argparse

BASE_PATH = "semantic_memory/courses"

TEMPLATE_HEAD = """
<!DOCTYPE html>
<html lang=\"en\">
<head>
  <meta charset=\"UTF-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\" />
  <title>{title}</title>
  <script src=\"https://cdn.tailwindcss.com\"></script>
</head>
<body class=\"bg-white text-gray-800 px-6 py-10 max-w-3xl mx-auto font-sans\">
"""

TEMPLATE_FOOT = """
</body>
</html>
"""

def create_course(params):
    title = params["title"]
    slug = params["slug"]
    path = os.path.join(BASE_PATH, slug)
    os.makedirs(os.path.join(path, "modules"), exist_ok=True)

    course_data = {
        "title": title,
        "slug": slug,
        "modules": []
    }

    with open(os.path.join(path, "course.json"), "w") as f:
        json.dump(course_data, f, indent=2)

    return {"status": "success", "message": f"Course '{title}' created at {path}"}

def create_module(params):
    slug = params["slug"]
    module_index = params["module_index"]
    module_data = {
        "title": params["title"],
        "video": params["video"],
        "text": params["text"]
    }
    mod_path = os.path.join(BASE_PATH, slug, "modules")
    os.makedirs(mod_path, exist_ok=True)
    path = os.path.join(mod_path, f"module-{module_index}.json")
    with open(path, "w") as f:
        json.dump(module_data, f, indent=2)
    return {"status": "success", "message": f"Module-{module_index} created."}

def add_module_to_course(params):
    slug = params["slug"]
    module_index = params["module_index"]
    course_path = os.path.join(BASE_PATH, slug, "course.json")
    if not os.path.exists(course_path):
        return {"status": "error", "message": "Course not found"}

    with open(course_path, "r") as f:
        data = json.load(f)

    ref = f"modules/module-{module_index}.json"
    if ref not in data["modules"]:
        data["modules"].append(ref)

    with open(course_path, "w") as f:
        json.dump(data, f, indent=2)

    return {"status": "success", "message": f"Module-{module_index} added to course."}

def generate_course_pages(params):
    slug = params["slug"]
    path = os.path.join(BASE_PATH, slug)
    course_file = os.path.join(path, "course.json")
    if not os.path.exists(course_file):
        return {"status": "error", "message": "Course not found"}

    with open(course_file, "r") as f:
        data = json.load(f)

    # index.html
    index_path = os.path.join(path, "index.html")
    with open(index_path, "w") as f:
        f.write(TEMPLATE_HEAD.format(title=data["title"]))
        f.write(f"<h1 class='text-3xl font-bold mb-6'>{data['title']}</h1>\n<ul class='list-disc pl-5'>\n")
        for i, ref in enumerate(data["modules"], 1):
            mod_file = os.path.join(path, ref)
            with open(mod_file, "r") as mf:
                mod = json.load(mf)
            f.write(f"<li><a class='text-blue-600 underline' href='module-{i}.html'>{mod['title']}</a></li>\n")
        f.write("</ul>\n")
        f.write(TEMPLATE_FOOT)

    # module-N.html
    for i, ref in enumerate(data["modules"], 1):
        mod_file = os.path.join(path, ref)
        with open(mod_file, "r") as mf:
            mod = json.load(mf)
        mod_path = os.path.join(path, f"module-{i}.html")
        with open(mod_path, "w") as f:
            f.write(TEMPLATE_HEAD.format(title=mod["title"]))
            f.write(f"<h2 class='text-2xl font-semibold mb-4'>{mod['title']}</h2>\n")
            f.write(f"<div class='mb-6'><iframe width='100%' height='315' src='{mod['video']}' frameborder='0' allowfullscreen></iframe></div>\n")
            f.write(f"<p class='mb-6'>{mod['text']}</p>\n")
            if i > 1:
                f.write(f"<a href='module-{i-1}.html' class='text-blue-600 mr-4'>&larr; Previous</a>")
            if i < len(data["modules"]):
                f.write(f"<a href='module-{i+1}.html' class='text-blue-600'>Next &rarr;</a>")
            f.write(TEMPLATE_FOOT)

    return {"status": "success", "message": f"Generated HTML pages for {slug}"}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action")
    parser.add_argument("--params")
    args = parser.parse_args()

    params = json.loads(args.params or "{}")

    if args.action == "create_course":
        result = create_course(params)
    elif args.action == "create_module":
        result = create_module(params)
    elif args.action == "add_module_to_course":
        result = add_module_to_course(params)
    elif args.action == "generate_course_pages":
        result = generate_course_pages(params)
    else:
        result = {"status": "error", "message": "Unknown action"}

    print(json.dumps(result, indent=2))

if __name__ == "__main__":
    main()

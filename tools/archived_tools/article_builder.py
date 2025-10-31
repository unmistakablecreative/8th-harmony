import os
import json


def create_article_blueprint(filename):
    with open(filename, 'w') as f:
        json.dump({"title": "", "sections": {}}, f, indent=2)
    return {"status": "success", "message": f"Created article blueprint: {filename}"}


def add_blog_section(filename, section_id, text, image_url):
    with open(filename, 'r') as f:
        data = json.load(f)
    data['sections'][section_id] = {"text": text, "image_url": image_url}
    with open(filename, 'w') as f:
        json.dump(data, f, indent=2)
    return {"status": "success", "message": f"Added section '{section_id}' to {filename}"}


def assemble_article(filename):
    with open(filename, 'r') as f:
        data = json.load(f)

    sections = data.get('sections', {})
    if not sections:
        raise ValueError("No sections defined in article.")

    ordered = []
    for section_id, section in sections.items():
        text = section.get('text', '')
        img = section.get('image_url')
        if img:
            img_md = f"![Image]({img})\n"
            ordered.append(img_md + text)
        else:
            ordered.append(text)

    content = "\n\n".join(ordered)
    slug = filename.replace('_blog.json', '').replace('.json', '')
    return {"status": "success", "content": content, "slug": slug}


def write_article_to_file(filename):
    assembled = assemble_article(filename)
    content = assembled["content"]
    slug = assembled["slug"]
    output_path = f"/orchestrate_user/orchestrate_exports/markdown/{slug}.md"
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, 'w') as f:
        f.write(content)
    return {"status": "success", "path": output_path}



def main(params):
    action = params.pop("action", None)  # ✅ Strip 'action' before dispatch
    if action in action_map:
        return action_map[action](**params)
    else:
        return {"status": "error", "message": f"Unknown action '{action}'"}

# ➕ Required for Orchestrate dispatch and CLI
action_map = {
    "create_article_blueprint": create_article_blueprint,
    "add_blog_section": add_blog_section,
    "assemble_article": assemble_article,
    "write_article_to_file": write_article_to_file
}

def cli():
    import argparse, json
    parser = argparse.ArgumentParser()
    parser.add_argument("action")
    parser.add_argument("--params")
    args = parser.parse_args()

    try:
        params = json.loads(args.params) if args.params else {}
        params["action"] = args.action
        result = main(params)
    except Exception as e:
        result = {"status": "error", "message": str(e)}

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    cli()




import json
import time
import os
import fnmatch
import requests
import random
from datetime import datetime
from zoneinfo import ZoneInfo
from requests_oauthlib import OAuth1Session

# --- Core Functions ---

def load_credential(key):
    try:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        cred_path = os.path.join(base_dir, "credentials.json")
        with open(cred_path, "r") as f:
            creds = json.load(f)
        return creds.get(key)
    except Exception:
        return None

def get_campaign_media(campaign_prefix, media_type="image"):
    """Find all media files for a campaign prefix - supports images and videos"""
    if media_type == "video":
        media_dir = "/Users/srinivas/Orchestrate Github/orchestrate-jarvis/semantic_memory/clips/"
        patterns = [f"{campaign_prefix}_*.mp4", f"{campaign_prefix}_*.mov"]
    else:
        media_dir = "/Users/srinivas/Orchestrate Github/orchestrate-jarvis/semantic_memory/images/"
        patterns = [f"{campaign_prefix}_*.png", f"{campaign_prefix}_*.jpg", f"{campaign_prefix}_*.jpeg"]
    
    try:
        files = os.listdir(media_dir)
        matching_files = []
        for pattern in patterns:
            matching_files.extend([f for f in files if fnmatch.fnmatch(f, pattern)])
        return sorted(set(matching_files))
    except OSError:
        return []

def assign_media_path(entry_key, media_type="image"):
    """Assign local media path based on entry key - works for images and videos"""
    try:
        parts = entry_key.split('_')
        
        if len(parts) < 3 or 'post' not in parts:
            return None
            
        post_index = parts.index('post')
        campaign_prefix = "_".join(parts[:post_index])
        
        post_num_str = parts[post_index + 1]
        post_num = int(post_num_str)
        
        campaign_media = get_campaign_media(campaign_prefix, media_type)
        if not campaign_media:
            return None
            
        media_index = (post_num - 1) % len(campaign_media)
        media_filename = campaign_media[media_index]
        
        if media_type == "video":
            media_dir = "/Users/srinivas/Orchestrate Github/orchestrate-jarvis/semantic_memory/clips/"
        else:
            media_dir = "/Users/srinivas/Orchestrate Github/orchestrate-jarvis/semantic_memory/images/"
            
        media_path = os.path.join(media_dir, media_filename)
        return media_path
        
    except (ValueError, IndexError):
        return None

def upload_media_to_twitter(media_path, oauth, media_type="image"):
    """Upload media to Twitter - handles both images and videos"""
    try:
        if not os.path.exists(media_path):
            return None
        
        if media_type == "video":
            return upload_video_to_twitter(media_path, oauth)
        else:
            return upload_image_to_twitter(media_path, oauth)
            
    except Exception:
        return None

def upload_image_to_twitter(image_path, oauth):
    """Upload image to Twitter - single-step process"""
    try:
        media_upload_url = "https://upload.twitter.com/1.1/media/upload.json"
        
        with open(image_path, 'rb') as image_file:
            files = {'media': image_file}
            response = oauth.post(media_upload_url, files=files)
            
        if response.status_code == 200:
            media_data = response.json()
            return media_data.get('media_id_string')
        return None
    except Exception:
        return None

def upload_video_to_twitter(video_path, oauth):
    """Upload video to Twitter - three-phase chunked upload"""
    try:
        file_size = os.path.getsize(video_path)
        media_upload_url = "https://upload.twitter.com/1.1/media/upload.json"
        
        ext = os.path.splitext(video_path)[1].lower()
        media_type = "video/mp4" if ext == ".mp4" else "video/quicktime"
        
        init_response = oauth.post(media_upload_url, data={
            "command": "INIT",
            "media_type": media_type,
            "total_bytes": file_size,
            "media_category": "tweet_video"
        })
        
        if init_response.status_code != 200:
            return None
            
        media_id = init_response.json()["media_id_string"]
        
        segment_index = 0
        with open(video_path, 'rb') as f:
            while True:
                chunk = f.read(4 * 1024 * 1024)
                if not chunk:
                    break
                    
                append_response = oauth.post(media_upload_url, data={
                    "command": "APPEND",
                    "media_id": media_id,
                    "segment_index": segment_index
                }, files={"media": chunk})
                
                if append_response.status_code != 204:
                    return None
                    
                segment_index += 1
        
        finalize_response = oauth.post(media_upload_url, data={
            "command": "FINALIZE",
            "media_id": media_id
        })
        
        if finalize_response.status_code != 200:
            return None
        
        processing_info = finalize_response.json().get("processing_info")
        if processing_info:
            state = processing_info.get("state")
            check_after_secs = processing_info.get("check_after_secs", 5)
            
            while state in ["pending", "in_progress"]:
                time.sleep(check_after_secs)
                
                status_response = oauth.get(media_upload_url, params={
                    "command": "STATUS",
                    "media_id": media_id
                })
                
                if status_response.status_code != 200:
                    return None
                    
                processing_info = status_response.json().get("processing_info", {})
                state = processing_info.get("state")
                check_after_secs = processing_info.get("check_after_secs", 5)
                
                if state == "failed":
                    return None
        
        return media_id
        
    except Exception:
        return None

def post_to_platform(params):
    text = params.get("text", "").strip()
    media_path = params.get("media_path")
    media_type = params.get("media_type", "image")
    
    if not text:
        return {"status": "error", "message": "Text is required."}

    TWITTER_API_KEY = load_credential("twitter_api_key")
    TWITTER_API_SECRET = load_credential("twitter_api_secret")
    TWITTER_ACCESS_TOKEN = load_credential("twitter_access_token")
    TWITTER_ACCESS_SECRET = load_credential("twitter_access_secret")

    if not all([TWITTER_API_KEY, TWITTER_API_SECRET, TWITTER_ACCESS_TOKEN, TWITTER_ACCESS_SECRET]):
        return {"status": "error", "message": "Missing Twitter credentials."}

    oauth = OAuth1Session(
        TWITTER_API_KEY,
        TWITTER_API_SECRET,
        TWITTER_ACCESS_TOKEN,
        TWITTER_ACCESS_SECRET
    )

    media_id = None
    if media_path:
        media_id = upload_media_to_twitter(media_path, oauth, media_type)

    url = "https://api.twitter.com/2/tweets"
    payload = {"text": text}
    
    if media_id:
        payload["media"] = {"media_ids": [media_id]}

    try:
        response = oauth.post(url, json=payload)
        response.raise_for_status()
        return {"status": "success", "message": "Tweet posted successfully", "data": response.json()}
    except Exception as e:
        return {"status": "error", "message": "Twitter API error", "error": str(e)}

def get_content_type_rule(content_type, rules):
    """Get rule for content type, with fallback logic"""
    if content_type in rules:
        return rules[content_type]
    
    fallback_order = ["articles", "default"]
    for fallback in fallback_order:
        if fallback in rules:
            return rules[fallback]
    
    if rules:
        return next(iter(rules.values()))
    
    return {}

def buffer_loop():
    """Main publishing loop - runs continuously"""
    while True:
        try:
            with open("data/campaign_rules.json", "r") as f:
                rules = json.load(f).get("entries", {})

            with open("data/post_queue.json", "r") as f:
                queue = json.load(f).get("entries", {})

            now = datetime.now(ZoneInfo("America/Los_Angeles"))
            today = now.strftime("%a").lower()
            now_time = now.strftime("%H:%M")
            today_date = now.strftime("%Y-%m-%d")

            posts_by_type = {}
            for post_key, post in queue.items():
                if post.get("status") != "scheduled":
                    continue
                
                content_type = post.get("content_type", "articles")
                if content_type not in posts_by_type:
                    posts_by_type[content_type] = []
                posts_by_type[content_type].append((post_key, post))

            for content_type, posts in posts_by_type.items():
                rule = get_content_type_rule(content_type, rules)
                
                if today not in rule.get("days", []):
                    continue

                timeslots = rule.get("timeslots", [])

                # Check if current time matches any timeslot (within 2 minute window)
                current_slot = None
                now_hour = now.hour
                now_minute = now.minute
                
                for slot in timeslots:
                    slot_hour, slot_minute = map(int, slot.split(":"))
                    
                    # Check if we're within 2 minutes of this timeslot
                    time_diff = abs((now_hour * 60 + now_minute) - (slot_hour * 60 + slot_minute))
                    
                    if time_diff <= 2:
                        current_slot = slot
                        break

                if not current_slot:
                    continue  # Not at any timeslot right now

                # Check if we've already posted in this specific timeslot today
                posted_in_current_slot = False
                for post in queue.values():
                    if (post.get("content_type", "articles") == content_type and 
                        post.get("status") == "published" and 
                        post.get("published_time", "").startswith(today_date)):
                        
                        pub_time = post.get("published_time", "")
                        if "T" in pub_time:
                            pub_hour_min = pub_time.split("T")[1][:5]
                            if pub_hour_min == current_slot:
                                posted_in_current_slot = True
                                break

                if not posted_in_current_slot and posts:
                    post_key, post = posts[0]
                    
                    media_type = rule.get("media_type", "image")
                    media_path = assign_media_path(post_key, media_type)
                    
                    full_content = f"{post.get('content', '').strip()}\n{post.get('link', '').strip()}"
                    
                    post_params = {"text": full_content}
                    if media_path:
                        post_params["media_path"] = media_path
                        post_params["media_type"] = media_type
                    
                    result = post_to_platform(post_params)
                    
                    post["status"] = "published"
                    post["published_time"] = now.isoformat()
                    post["response"] = result
                    if media_path:
                        media_filename = os.path.basename(media_path)
                        if media_type == "video":
                            post["media_url"] = f"https://grossly-guiding-elk.ngrok-free.app/semantic_memory/clips/{media_filename}"
                        else:
                            post["media_url"] = f"https://grossly-guiding-elk.ngrok-free.app/semantic_memory/images/{media_filename}"
                        post["media_type"] = media_type

            with open("data/post_queue.json", "w") as f:
                json.dump({"entries": queue}, f, indent=2)

        except Exception:
            pass

        time.sleep(60)

    return {"status": "running", "message": "Buffer engine loop initiated"}



def shuffle_queue(params):
    """Shuffle the post queue randomly"""
    filename = "data/post_queue.json"
    
    try:
        if not os.path.exists(filename):
            return {"status": "error", "message": "post_queue.json not found"}
        
        with open(filename, "r") as f:
            data = json.load(f)
        
        entries = data.get("entries", {})
        
        scheduled_posts = [(k, v) for k, v in entries.items() if v.get("status") == "scheduled"]
        
        if not scheduled_posts:
            return {"status": "success", "message": "No scheduled posts to shuffle"}
        
        random.shuffle(scheduled_posts)
        
        shuffled_entries = {}
        
        for k, v in entries.items():
            if v.get("status") != "scheduled":
                shuffled_entries[k] = v
        
        for k, v in scheduled_posts:
            shuffled_entries[k] = v
        
        data["entries"] = shuffled_entries
        
        with open(filename, "w") as f:
            json.dump(data, f, indent=2)
        
        return {
            "status": "success",
            "message": f"Shuffled {len(scheduled_posts)} scheduled posts",
            "shuffled_count": len(scheduled_posts)
        }
        
    except Exception as e:
        return {"status": "error", "message": str(e)}

def add_social_post(params):
    """Add social post - uses 'text' param"""
    filename = "data/post_queue.json"
    entry_key = params.get("entry_key")
    
    if not entry_key:
        return {"status": "error", "message": "Missing required field: entry_key"}
    
    campaign_id = params.get("campaign_id")
    text = params.get("text")
    link = params.get("link", "")
    content_type = params.get("content_type", "articles")
    
    if not campaign_id or not text:
        return {"status": "error", "message": "Missing required fields: campaign_id, text"}

    entry = {
        "campaign_id": campaign_id,
        "content": text,
        "link": link,
        "content_type": content_type,
        "status": "scheduled",
        "created_time": datetime.utcnow().isoformat()
    }

    try:
        with open("data/campaign_rules.json", "r") as f:
            rules = json.load(f).get("entries", {})
        rule = rules.get(content_type, {})
        media_type = rule.get("media_type", "image")
    except:
        media_type = "image"

    media_path = assign_media_path(entry_key, media_type)
    if media_path:
        media_filename = os.path.basename(media_path)
        if media_type == "video":
            entry["media_url"] = f"https://grossly-guiding-elk.ngrok-free.app/semantic_memory/clips/{media_filename}"
        else:
            entry["media_url"] = f"https://grossly-guiding-elk.ngrok-free.app/semantic_memory/images/{media_filename}"
        entry["media_type"] = media_type

    try:
        if os.path.exists(filename):
            with open(filename, "r") as f:
                data = json.load(f)
        else:
            data = {"entries": {}}

        data["entries"][entry_key] = entry

        with open(filename, "w") as f:
            json.dump(data, f, indent=2)

        return {
            "status": "success", 
            "message": "Post added to queue", 
            "post_id": entry_key,
            "media_url": entry.get("media_url"),
            "media_type": entry.get("media_type")
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}

def batch_add_social_post(params):
    """Add multiple posts - uses 'text' param"""
    posts = params.get("posts", [])
    filename = "data/post_queue.json"

    if not isinstance(posts, list):
        return {"status": "error", "message": "posts must be a list of entries"}

    try:
        with open("data/campaign_rules.json", "r") as f:
            rules = json.load(f).get("entries", {})
    except:
        rules = {}

    try:
        if os.path.exists(filename):
            with open(filename, "r") as f:
                data = json.load(f)
        else:
            data = {"entries": {}}

        inserted = []
        for entry in posts:
            entry_key = entry.get("entry_key")
            if not entry_key or not entry.get("campaign_id") or not entry.get("text"):
                continue
            
            content_type = entry.get("content_type", "articles")
            rule = rules.get(content_type, {})
            media_type = rule.get("media_type", "image")
                
            post_data = {
                "campaign_id": entry["campaign_id"],
                "content": entry["text"],
                "link": entry.get("link", ""),
                "content_type": content_type,
                "status": "scheduled",
                "created_time": datetime.utcnow().isoformat()
            }
            
            media_path = assign_media_path(entry_key, media_type)
            if media_path:
                media_filename = os.path.basename(media_path)
                if media_type == "video":
                    post_data["media_url"] = f"https://grossly-guiding-elk.ngrok-free.app/semantic_memory/clips/{media_filename}"
                else:
                    post_data["media_url"] = f"https://grossly-guiding-elk.ngrok-free.app/semantic_memory/images/{media_filename}"
                post_data["media_type"] = media_type
            
            data["entries"][entry_key] = post_data
            inserted.append(entry_key)

        with open(filename, "w") as f:
            json.dump(data, f, indent=2)

        return {"status": "success", "inserted_count": len(inserted), "post_ids": inserted}
    except Exception as e:
        return {"status": "error", "message": str(e)}

def update_post_entry(params):
    """Update post entry"""
    post_id = params.get("post_id")
    filename = "data/post_queue.json"

    if not post_id:
        return {"status": "error", "message": "Missing post_id"}

    update_fields = {k: v for k, v in params.items() if k != "post_id"}
    
    if not update_fields:
        return {"status": "error", "message": "No update fields provided"}

    try:
        if not os.path.exists(filename):
            return {"status": "error", "message": "post_queue.json not found"}

        with open(filename, "r") as f:
            data = json.load(f)

        entries = data.get("entries", {})
        if post_id not in entries:
            return {"status": "error", "message": f"Post ID '{post_id}' not found"}

        entries[post_id].update(update_fields)

        with open(filename, "w") as f:
            json.dump(data, f, indent=2)

        return {
            "status": "success", 
            "message": f"Post '{post_id}' updated with {len(update_fields)} fields", 
            "updated_fields": list(update_fields.keys())
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}

def get_post_entry(params):
    """Get a specific post by ID"""
    post_id = params.get("post_id")
    filename = "data/post_queue.json"
    
    if not post_id:
        return {"status": "error", "message": "Missing post_id"}
    
    try:
        if not os.path.exists(filename):
            return {"status": "error", "message": "post_queue.json not found"}

        with open(filename, "r") as f:
            data = json.load(f)

        entries = data.get("entries", {})
        if post_id not in entries:
            return {"status": "error", "message": f"Post ID '{post_id}' not found"}

        return {"status": "success", "entry": entries[post_id]}
    except Exception as e:
        return {"status": "error", "message": str(e)}

def list_posts_by_campaign(params):
    """List all posts for a specific campaign"""
    campaign_id = params.get("campaign_id")
    filename = "data/post_queue.json"
    
    if not campaign_id:
        return {"status": "error", "message": "Missing campaign_id"}
    
    try:
        if not os.path.exists(filename):
            return {"status": "error", "message": "post_queue.json not found"}

        with open(filename, "r") as f:
            data = json.load(f)

        entries = data.get("entries", {})
        campaign_posts = {
            k: v for k, v in entries.items() 
            if v.get("campaign_id") == campaign_id
        }

        return {
            "status": "success", 
            "campaign_id": campaign_id,
            "posts": campaign_posts,
            "count": len(campaign_posts)
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}

def add_campaign_rule(params):
    """Add campaign rule"""
    content_type = params.get("content_type")
    days = params.get("days", [])
    timeslots = params.get("timeslots", [])
    max_posts = params.get("max_posts_per_day", 10)
    media_type = params.get("media_type", "image")
    filename = "data/campaign_rules.json"

    if not content_type:
        return {"status": "error", "message": "Missing required field: content_type"}

    new_rule = {
        "days": days,
        "timeslots": timeslots,
        "max_posts_per_day": max_posts,
        "media_type": media_type
    }

    try:
        if os.path.exists(filename):
            with open(filename, "r") as f:
                data = json.load(f)
        else:
            data = {"entries": {}}

        data["entries"][content_type] = new_rule

        with open(filename, "w") as f:
            json.dump(data, f, indent=2)

        return {"status": "success", "message": f"Content type rule '{content_type}' added with media_type: {media_type}"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

def update_campaign_rule(params):
    """Update campaign rule"""
    content_type = params.get("content_type")
    filename = "data/campaign_rules.json"

    if not content_type:
        return {"status": "error", "message": "Missing content_type"}

    update_fields = {k: v for k, v in params.items() if k != "content_type"}
    
    if not update_fields:
        return {"status": "error", "message": "No update fields provided"}

    try:
        if not os.path.exists(filename):
            return {"status": "error", "message": "campaign_rules.json not found"}

        with open(filename, "r") as f:
            data = json.load(f)

        entries = data.get("entries", {})
        if content_type not in entries:
            return {"status": "error", "message": f"Content type '{content_type}' not found"}

        entries[content_type].update(update_fields)

        with open(filename, "w") as f:
            json.dump(data, f, indent=2)

        return {
            "status": "success", 
            "message": f"Content type '{content_type}' updated with {len(update_fields)} fields",
            "updated_fields": list(update_fields.keys())
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}

def get_campaign_rule(params):
    """Get a specific campaign rule"""
    content_type = params.get("content_type")
    filename = "data/campaign_rules.json"
    
    if not content_type:
        return {"status": "error", "message": "Missing content_type"}
    
    try:
        if not os.path.exists(filename):
            return {"status": "error", "message": "campaign_rules.json not found"}

        with open(filename, "r") as f:
            data = json.load(f)

        entries = data.get("entries", {})
        if content_type not in entries:
            return {"status": "error", "message": f"Content type '{content_type}' not found"}

        return {"status": "success", "rule": entries[content_type]}
    except Exception as e:
        return {"status": "error", "message": str(e)}

def list_all_campaigns(params):
    """List all campaign rules"""
    filename = "data/campaign_rules.json"
    
    try:
        if not os.path.exists(filename):
            return {"status": "error", "message": "campaign_rules.json not found"}

        with open(filename, "r") as f:
            data = json.load(f)

        return {"status": "success", "campaigns": data.get("entries", {})}
    except Exception as e:
        return {"status": "error", "message": str(e)}

def main():
    import argparse, json
    parser = argparse.ArgumentParser()
    parser.add_argument('action')
    parser.add_argument('--params')
    args = parser.parse_args()
    params = json.loads(args.params) if args.params else {}

    if args.action == 'run_engine':
        result = buffer_loop()
    elif args.action == 'buffer_loop':
        result = buffer_loop()
    elif args.action == 'post_to_platform':
        result = post_to_platform(params)
    elif args.action == 'add_social_post':
        result = add_social_post(params)
    elif args.action == 'batch_add_social_post':
        result = batch_add_social_post(params)
    elif args.action == 'update_post_entry':
        result = update_post_entry(params)
    elif args.action == 'get_post_entry':
        result = get_post_entry(params)
    elif args.action == 'list_posts_by_campaign':
        result = list_posts_by_campaign(params)
    elif args.action == 'add_campaign_rule':
        result = add_campaign_rule(params)
    elif args.action == 'update_campaign_rule':
        result = update_campaign_rule(params)
    elif args.action == 'get_campaign_rule':
        result = get_campaign_rule(params)
    elif args.action == 'list_all_campaigns':
        result = list_all_campaigns(params)
    elif args.action == 'shuffle_queue':
        result = shuffle_queue(params)
    else:
        result = {'status': 'error', 'message': f'Unknown action {args.action}'}

    print(json.dumps(result, indent=2))

if __name__ == "__main__":
    main()
import time
import requests
import json
from datetime import datetime, timedelta
import re
import markdown
from bs4 import BeautifulSoup
from langdetect import detect_langs, LangDetectException as Lang_e
import logging
from winners_list import update_winners_list


# logger
def get_logger():
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.INFO)
    handler = logging.FileHandler("community_post_checker.log", mode="a")
    formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    return logger


logger = get_logger()


# INTERACTION WITH HIVE API


# Send request, get response, return decoded JSON response
def get_response(data, session: requests.Session):
    urls = [
        "https://api.deathwing.me",
        "https://api.hive.blog",
        "https://hive-api.arcange.eu",
        "https://api.openhive.network"
    ]
    for url in urls:
        request = requests.Request("POST", url=url, data=data).prepare()
        response_json = session.send(request, allow_redirects=False)
        if response_json.status_code == 502:
            continue
        response = response_json.json().get("result", [])
        if len(response) == 0:
            logger.warning(f"{response_json.json()} from this {data}")
        return response


# CHECK REQUIREMENTS OF THE POSTS // API INTERACTION --> NO


# Check it target language is among the top languages and number of languages
def text_language(text):
    try:
        languages = detect_langs(text)
        num_languages = len(languages)

        # Double-check the presence of the target language to avoid false negatives
        if not any(lang.lang == "it" for lang in languages):
            text_length = len(text)
            half_length = text_length // 2
            first_half = text[:half_length]
            second_half = text[half_length:]
            for _ in range(2):
                languages = detect_langs(first_half)
                if any(lang.lang == "it" for lang in languages):
                    num_languages = 2  # Set to 2 because there's another language
                    break
                languages = detect_langs(second_half)
                if any(lang.lang == "it" for lang in languages):
                    num_languages = 2  # Same as above
                    break
    except Lang_e:
        logger.error(f"Language error: {Lang_e}")
        return False, 0

    return num_languages


# Clean text before converting and counting words
def clean_markdown(md_text):
    # Remove images
    md_text = re.sub(r"!\[.*?]\(.*?\)", "", md_text)

    # Remove hyperlinks
    md_text = re.sub(r"\[(.*?)]\(.*?\)", r"\1", md_text)

    return md_text


# Convert to plain text and check post's length
def convert_and_count_words(md_text):
    cleaned_md_text = clean_markdown(md_text)
    html = markdown.markdown(cleaned_md_text, output_format="html")

    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text()

    words = re.findall(r"\b\w+\b", text)
    return len(words)


    # CHECK REQUIREMENTS OF THE POSTS // API INTERACTION --> YES


# Check if target account commented a post in the past 7 days in the target community
def replies(author, permlink, seven_days, session: requests.Session):
    # Get replies from target author
    data = (
        f'{{"jsonrpc":"2.0", "method":"bridge.get_account_posts", '
        f'"params":{{"sort":"comments", "account": "{author}", "limit": 100}}, "id":1}}'
    )

    f'{{"jsonrpc":"2.0", "method":"condenser_api.get_content_replies", '
    f'"params":["{author}", "{permlink}"], "id":1}}'

    replies = get_response(data, session)
    replies_num = 0
    valid_reply = False
    for reply in replies:
        reply_time = reply["created"]
        reply_time_formatted = datetime.strptime(reply_time, "%Y-%m-%dT%H:%M:%S")

        if reply_time_formatted < seven_days:
            break

        if "hive-146620" not in reply.get("community", []):
            continue  # If the comment is not in the target community, skip

        if reply["children"] == 1 and reply["parent_author"] != author:
            valid_reply = True  # Look for comments to other authors

        replies_num += 1

    return valid_reply, replies_num


# Check if target account voted in one of the 3 last polls
def has_voted_poll(last_polls, author, session: requests.Session):
    today = datetime.now()
    three_weeks_ago = today - timedelta(days=21, hours=23)
    num = -1
    polls_voted = 0
    while True:
        # Get all custom operations from target account, poll votes included
        data = (
            f'{{"jsonrpc":"2.0", "method":"condenser_api.get_account_history", '
            f'"params":["{author}", {num}, 1000, 262144], "id":1}}'
        )
        custom_json = get_response(data, session)
        for op in custom_json:
            link = op[1]["op"][1]["id"]
            if link in last_polls:
                polls_voted += 1
        timestamp = custom_json[0][1]["timestamp"]
        timestamp_formatted = datetime.strptime(timestamp, "%Y-%m-%dT%H:%M:%S")
        if timestamp_formatted < three_weeks_ago:
            return polls_voted
        num = custom_json[0][0]


# Found and check eligible posts published in the last 7 days in the target community
def eligible_posts(session: requests.Session):
    today = datetime.now()
    seven_days = today - timedelta(days=6, hours=23)

    less_than_seven_days = True

    authors = [
        "libertycrypto27", 
        "will91", 
        "steveguereschi", 
        "lozio71", 
        "harbiter", 
        "arc7icwolf"
    ]

    for author in authors:
        while less_than_seven_days:
            # Get posts published by the target author
            data = (
                f'{{"jsonrpc":"2.0", "method":"bridge.get_account_posts", '
                f'"params":{{"sort":"posts", "account": "{author}", "limit": 20}}, "id":1}}'
            )
            posts = get_response(data, session)
            for post in posts:
                author = post["author"]
                category = post["category"]
                body = post["body"]
                created = post["created"]
                permlink = post["permlink"]
                title = post["title"]

                if category != "hive-146620":
                    continue  # Skip post published in a different community

                created_formatted = datetime.strptime(created, "%Y-%m-%dT%H:%M:%S")
                if created_formatted < seven_days:
                    less_than_seven_days = False
                    print("No more posts less than seven days older found")
                    break  # Stop if post is more than 7 days old

                lang_num = text_language(body)

                word_count = convert_and_count_words(body)

                if lang_num == 2:
                    word_count = word_count // 2
                    
                    
                replies_num = replies(author, permlink, seven_days, session)

                polls_voted = has_voted_poll(last_polls, author, session)
                if polls_voted == 0:
                    continue

                author_stats = (
                    f"- **{author}** made **{replies_num} comments**"
                    f" and voted in **{polls_voted} polls**"
                )
                if author_stats not in authors_stats:
                    authors_stats.append(author_stats)

                beneficiary = "no"
                beneficiary_weight_formatted = ""
                for beneficiary in beneficiaries:
                    if beneficiary.get("account", []) == "balaenoptera":
                        beneficiary_weight = beneficiary.get("weight", [])
                        beneficiary_weight_formatted = f"for {int(beneficiary_weight / 100)}%"
                        beneficiary = "yes"
                        break

                message = (
                    f"{i}) {author} published ['{title}'](https://www.peakd.com/@{author}/{permlink})"
                    f" ---> balaenoptera as beneficiary? {beneficiary} {beneficiary_weight_formatted}"
                )

                entries.append(message)

                print(message)

                i += 1

    with open("entries.txt", "w", newline="", encoding="utf-8") as file:
        for entry in entries:
            file.write(f"{entry}\n")

    with open("authors_list.txt", "w", newline="", encoding="utf-8") as file:
        authors_stats.sort()
        for author_stats in authors_stats:
            file.write(f"{author_stats}\n")


def main():
    start = time.time()

    try:
        with requests.Session() as session:
            eligible_posts(session)
    except (json.JSONDecodeError, KeyError) as e:
        logger.error(f"JSON decode error or missing key: {e}")
    except Exception as e:
        logger.error(f"An error occurred: {e}")

    update_winners_list(session)

    elapsed_time = time.time() - start
    print(f"Work completed in {elapsed_time:.2f} seconds")

    return True


if __name__ == "__main__":
    main()
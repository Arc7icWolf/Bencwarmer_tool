import requests
import json
from datetime import datetime, timedelta
import re
import markdown
from bs4 import BeautifulSoup
from langdetect import detect_langs, LangDetectException as Lang_e
import logging
import streamlit as st


# logger
def get_logger():
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.INFO)
    handler = logging.FileHandler("tool.log", mode="a")
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
        "https://api.openhive.network",
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


# Check number of languages
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


# Get posts amount for target author
def posts(author, seven_days, session: requests.Session):
    data = (
        f'{{"jsonrpc":"2.0", "method":"bridge.get_account_posts", '
        f'"params":{{"sort":"posts", "account": "{author}", "limit": 20}}, "id":1}}'
    )
    posts = get_response(data, session)

    valid_posts = []

    for post in posts:
        category = post["category"]
        created = post["created"]

        created_formatted = datetime.strptime(created, "%Y-%m-%dT%H:%M:%S")
        if created_formatted < seven_days:
            break  # Stop if post is more than 7 days old

        if category == "hive-146620":
            valid_posts.append(post)

    return valid_posts, len(valid_posts)


# Get total replies amount from target author in the target community
def replies(author, seven_days, session: requests.Session):
    data = (
        f'{{"jsonrpc":"2.0", "method":"bridge.get_account_posts", '
        f'"params":{{"sort":"comments", "account": "{author}", "limit": 100}}, "id":1}}'
    )
    replies = get_response(data, session)

    replies_num = 0
    replies_length = 0

    for reply in replies:
        reply_time = reply["created"]
        reply_time_formatted = datetime.strptime(reply_time, "%Y-%m-%dT%H:%M:%S")
        reply_body = reply["body"]

        if reply_time_formatted < seven_days:
            break

        if "hive-146620" not in reply.get("community", []):
            continue  # If the comment is not in the target community, skip

        word_count = convert_and_count_words(reply_body)

        replies_length += word_count

        replies_num += 1

    return replies_num, replies_length


# Get total replies amount for target post from target author
def post_replies(author, permlink, session: requests.Session):
    data = (
        f'{{"jsonrpc":"2.0", "method":"condenser_api.get_content_replies", '
        f'"params":["{author}", "{permlink}"], "id":1}}'
    )
    post_replies = get_response(data, session)

    return len(post_replies)


# Get total votes amount for target post from target author
def votes(author, permlink, session: requests.Session):
    data = (
        f'{{"jsonrpc":"2.0", "method":"condenser_api.get_active_votes", '
        f'"params":["{author}", "{permlink}"], "id":1}}'
    )

    votes = get_response(data, session)

    return len(votes)


# Found and check eligible posts published in the last 7 days in the target community
def eligible_posts(authors, session: requests.Session):
    today = datetime.now()
    seven_days = today - timedelta(days=6, hours=23)

    entries = []

    for author in authors:
        valid_posts, total_posts = posts(author, seven_days, session)
        total_replies, total_replies_length = replies(author, seven_days, session)

        total_post_replies = 0
        total_votes = 0
        total_words = 0

        for post in valid_posts:
            body = post["body"]
            permlink = post["permlink"]

            lang_num = text_language(body)
            word_count = convert_and_count_words(body)
            if lang_num == 2:
                word_count = word_count // 2

            total_words += word_count

            replies_num = post_replies(author, permlink, session)
            total_post_replies += replies_num

            votes_num = votes(author, permlink, session)
            total_votes += votes_num

        # Avoid division by zero
        if total_posts == 0:
            total_posts = 1
        if total_replies == 0:
            total_replies = 1
        
        formula = (
            (total_words / total_posts * 0.5)
            + (total_replies_length / total_replies * 10)
            + (total_votes / total_posts * 0.01)
            + (total_post_replies / total_posts * 0.2)
        )

        result = (
            f"- **{author}** ha pubblicato {total_posts} post "
            f"per un totale di {total_words} parole, "
            f"ottenendo {total_post_replies} risposte "
            f"e {total_votes} voti, "
            f"ed effettuato {total_replies} commenti "
            f"per un totale di {total_replies_length} parole, "
            f"per un punteggio finale di {formula:.2f} punti."
        )

        entries.append(result)

    entries.sort(key=lambda x: float(x.split()[-2]), reverse=True)
    logger.info(entries)
    return entries


def main(authors):
    try:
        with requests.Session() as session:
            entries = eligible_posts(authors, session)
    except (json.JSONDecodeError, KeyError) as e:
        logger.error(f"JSON decode error or missing key: {e}")
        st.error(f"JSON decode error or missing key: {e}")
        return
    except Exception as e:
        logger.error(f"An error occurred: {e}")
        st.error(f"An error occurred: {e}")
        return
    st.write("### Risultato degli ultimi 7 giorni:")
    with open("entries.txt", "w", newline="", encoding="utf-8") as file:
        for entry in entries:
            st.markdown(entry)
            file.write(f"{entry}\n")


if __name__ == "__main__":
    st.title("Engagement Contest, by Bencwarmer")
    # Input box to insert one or more usernames, separated by a comma
    authors_input = st.text_input("Inserisci uno o più username separati da virgola: ")
    authors = [author.strip() for author in authors_input.split(",") if author.strip()]
    if st.button("Avvia analisi dei dati"):
        if authors:
            main(authors)
        else:
            st.warning("Nessun autore inserito. Inserisci almeno uno username.")

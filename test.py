import requests
import json

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
        return response


def get_votes(author, session: requests.Session):
    data = (
        f'{{"jsonrpc":"2.0", "method":"condenser_api.get_account_history", '
        f'"params":["{author}", -1, 1000, 1], "id":1}}'
    )
    votes = get_response(data, session)
    for vote in votes[-4:-1]:
        print(vote)


def main():
    author = "arc7icwolf"
    with requests.Session() as session:
        get_votes(author, session)


if __name__ == "__main__":
    main()
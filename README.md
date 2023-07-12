# Animelon Download

Command line downloader for https://animelon.com/

## Args:

```
usage: animelon_dl.py [-h] [--dir PATH] [--subs_only] [--quality  [...]]  [...]
```

### Mandatory:

- `urls`: One or more series or video page URLs. This arg must come after all other args.

    To enter multiple URLs follow the following format:

    ```
    animelon_dl.py url1 url2 url3
    ```

### Optional:

- `--dir`: Directory path to save files to. Default: `./`.

- `--subs_only`: Only download subtitles. Default: `false`.

- `--quality`: List of quality priorities from highest to lowest priority. Default: `"ozez stz tsz"`.

    From highest to lowest quality: "ozez stz tsz".

- `--sleep`: Time in seconds to sleep between requests. Default: `5`.

## Dependencies

Python 3: [Download link](https://www.python.org/downloads/)

Python `requests` and `pycryptodome` modules: To install them, enter the following command in cmd or a terminal:

```
pip install requests pycryptodome
```
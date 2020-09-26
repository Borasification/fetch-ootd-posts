# Fetch OOTD Post from Borasification Forum

This project is meant to fetch the best OOTD posts of the week posted on the Borasification Forum.
It leverages Discourse API and it requires an API key that can be obtained from the admin pannel of the Borasification Forum

## Install
`$ pip install -r requirements.txt`

## Usage
Ask for an API Key and put it in `config.py` file together with your Borasification `username`.

Simply run `./fetch_ootd_posts {start_date} {end_date}` example `./fetch_ootd_posts 2020-09-21 2020-09-28`. The posts from the `start_date` are included and the posts from the `end_date` are excluded. If you want to fetch to posts from `2020-09-21` to `2020-09-27` , run the command ``./fetch_ootd_posts 2020-09-21 2020-09-28`.

The script generates two files
1. `output/{start_date}-{end_date}/images/images_url.txt` containing the url of the OOTD images. CAVEATS: Some urls might not be images and some are url from external image hosting. I didn't yet added the logic to get the proper image urls from those urls.
2. `output/{start_date}-{end_date}/posts/ordered_ootd_posts.txt` a file containing some details about each posts. The file is ordered by number of likes. I typically use this file to generate the best-off of the week.

## Download images
I use Aria2 to download images from the `ìmages_url.txt` file.

Go to the `output/{start_date}-{end_date}/images/` directory and run `aria2c -i images_url.txt`. This will download all images in the current directory.

## Download to Imgur
As I am filtering some images manually, I haven't integrated the Imgur API to automatically download images to Imgur.
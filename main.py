from fastapi import FastAPI, Request, UploadFile, File
from moviepy.editor import ImageClip, concatenate_videoclips, TextClip
from gtts import gTTS
import os

from requests import request
    


from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from dotenv import load_dotenv
from googleapiclient.discovery import build
from pytube import YouTube
from youtube_transcript_api import YouTubeTranscriptApi
import cv2
import os
from hugchat.login import Login
from hugchat import hugchat
from hugchat.message import Message
import openai

load_dotenv()

app = FastAPI()

@app.get("/")
async def root():
    # text = "Hello, this is a test."
    # tts = gTTS(text=text, lang='en')
    # tts.save("output.mp3")
    # os.system("output.mp3")
    return {"message": "Hello World"}

def create_video(images_folder, text, output_path):
    # Get all image files from the folder
    image_files = sorted([f for f in os.listdir(images_folder) if f.endswith(('.png', '.jpg', '.jpeg'))])
    
    # Create ImageClips from images
    clips = [ImageClip(os.path.join(images_folder, img)).set_duration(3) for img in image_files]

    # Add text narration
    text_clip = TextClip(text, fontsize=30, color='white').set_duration(len(clips) * 3)
    text_clip = text_clip.set_pos(('center', 'bottom'))

    # Concatenate ImageClips and text clip
    final_clip = concatenate_videoclips(clips)
    final_clip = final_clip.set_audio(text_clip.audio)

    # Write the final video to output_path
    final_clip.write_videofile(output_path, codec='libx264', fps=24)

@app.post("/generate_video")
async def generate_video(request: Request) :
    try:
        data = await request.json()
        output_path = "output_video.mp4"
        
        text =  data.get("text", "Default text if not provided in the request")
        images_folder = data.get("images_folder", None)
        with open(images_folder, "wb") as buffer:
            buffer.write(images_folder.file.read())
        create_video(images_folder, text, output_path)
    except Exception as e:
        return str(e)
    
    



# Setting API keys
yt_api_key = os.environ.get("yt_api_key")
huggingface_username = os.environ.get("huggingface_username")
huggingface_pwd = os.environ.get("huggingface_pwd")
openai_api_key = os.environ.get("openai_api_key")

# Set OpenAI API key
openai.api_key = openai_api_key


@app.get("/process_video")
async def process_video(video_url: str, num_frames: int = 5):
    try:
        # Extract video ID from the video link
        video_id = video_url.split('v=')[1]

        # Get the transcript for the video
        youtube = build('youtube', 'v3', developerKey=yt_api_key)
        captions = youtube.captions().list(part='snippet', videoId=video_id).execute()
        caption = captions['items'][0]['id']

        video_response = youtube.videos().list(part='snippet', id=video_id).execute()
        thumbnails = video_response['items'][0]['snippet']['thumbnails']

        transcript_list = YouTubeTranscriptApi.get_transcript(video_id)
        transcript_txt = ""

        for transcript in transcript_list:
            transcript_txt += transcript['text']

        summary = ""
        images = []

        if transcript_txt != "":
            # Log in to huggingface and grant authorization to huggingchat
            sign = Login(huggingface_username, huggingface_pwd)
            cookies = sign.login()

            # Save cookies to the local directory
            cookie_path_dir = "./cookies_snapshot"
            sign.saveCookiesToDir(cookie_path_dir)

            # Create a ChatBot
            chatbot = hugchat.ChatBot(cookies=cookies.get_dict())

            # Extract the summary from the response
            message = chatbot.query(
                "Summarize in 10 lines if the given data is more than 10 lines: " + transcript_txt)
            print(message[0],'ytr')
            # Extract the text from the Message object
            summary = message.text if hasattr(
                message, 'text') else str(message)

        try:
            # Capture frames directly from the YouTube video stream
            output_frames_folder = "frames"
            images = capture_frames(
                video_url, output_frames_folder, num_frames)
        except Exception as e:
            print(f"Error capturing frames: {e}")

        return JSONResponse(content={ "success": True,"summary": summary, "images": images})

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Error processing video: {str(e)}")


def capture_frames(video_url, output_folder='frames', num_frames=5):
    image_paths = []
    try:
        yt = YouTube(video_url)
        stream = yt.streams.filter(file_extension='mp4', res='360p').first()

        cap = cv2.VideoCapture(stream.url)
        frame_count = 0
        success, image = cap.read()

        while success and frame_count < num_frames:
            frame_count += 1
            frame_path = f"{output_folder}/frame_{frame_count}.png"
            cv2.imwrite(frame_path, image)
            image_paths.append(os.path.abspath(frame_path))
            success, image = cap.read()

        cap.release()
        print(f"{num_frames} frames captured.")
    except Exception as e:
        print(f"Error capturing frames: {e}")

    return image_paths
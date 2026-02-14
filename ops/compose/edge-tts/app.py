import tempfile
import os
from fastapi import FastAPI
from fastapi.responses import FileResponse
from pydantic import BaseModel
import edge_tts
import uuid

app = FastAPI()

class SpeechRequest(BaseModel):
    input: str
    voice: str = "en-US-AriaNeural"

@app.post("/v1/audio/speech")
async def generate_speech(req: SpeechRequest):
    communicate = edge_tts.Communicate(req.input, req.voice)
    filename = f"{uuid.uuid4()}.mp3"
    path = os.path.join(tempfile.gettempdir(), filename)
    await communicate.save(path)
    return FileResponse(path, media_type="audio/mpeg", background=None)

@app.get("/voices")
async def list_voices():
    voices = await edge_tts.list_voices()
    return voices

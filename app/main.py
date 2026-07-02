from fastapi import FastAPI
from app.routers import genomes

app = FastAPI(title="NCBI Genome API", version="0.1.0")
app.include_router(genomes.router)

@app.get("/")
async def root():
    return {"status": "ok"}
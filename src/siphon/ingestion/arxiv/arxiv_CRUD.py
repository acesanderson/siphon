from pymongo import MongoClient
from Paper import Paper

client = MongoClient("mongodb://localhost:27017/")
db = client["arxiv"]
papers_collection = db["papers"]


def get_a_paper(papers_collection=papers_collection) -> Paper:
    """
    Get a paper from the MongoDB collection.
    """
    result = papers_collection.find_one()
    return Paper(**result) if result else None


def get_all_papers(papers_collection=papers_collection) -> list[Paper]:
    """
    Get all papers from the MongoDB collection.
    """
    results = papers_collection.find()
    return [Paper(**result) for result in results]


def get_all_ids(papers_collection=papers_collection) -> set[str]:
    """
    Get all paper IDs from the MongoDB collection.
    """
    results = papers_collection.find({}, {"id": 1})
    return {result["id"] for result in results}


def get_paper_by_id(paper_id: str, papers_collection=papers_collection) -> Paper:
    """
    Get a paper by its ID from the MongoDB collection.
    """
    result = papers_collection.find_one({"id": paper_id})
    return Paper(**result) if result else None

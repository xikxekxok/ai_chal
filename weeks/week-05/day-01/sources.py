from dataclasses import dataclass

GUTENBERG_URL = "https://www.gutenberg.org/ebooks/{id}.txt.utf-8"


@dataclass(frozen=True)
class Book:
    id: str
    title: str
    author: str

    @property
    def url(self) -> str:
        return GUTENBERG_URL.format(id=self.id)

    @property
    def filename(self) -> str:
        return f"{self.id}.txt"


BOOKS: list[Book] = [
    Book(
        id="14732",
        title="The Adventures of Unc' Billy Possum",
        author="Thornton W. Burgess",
    ),
    Book(
        id="50881",
        title="'Possum",
        author="Mary Grant Bruce",
    ),
    Book(
        id="2441",
        title="The Burgess Animal Book for Children",
        author="Thornton W. Burgess",
    ),
    Book(
        id="14958",
        title='Mother West Wind "Why" Stories',
        author="Thornton W. Burgess",
    ),
    Book(
        id="37199",
        title="Ecology of the Opossum",
        author="Fitch & Sandidge",
    ),
    Book(
        id="59475",
        title="Wild Animals of North America",
        author="Edward W. Nelson",
    ),
    Book(
        id="43558",
        title="The Sandman's Hour",
        author="Abbie Phillips Walker",
    ),
    Book(
        id="60659",
        title="Wild Kindred",
        author="Jean M. Thompson",
    ),
]

BOOK_BY_ID = {book.id: book for book in BOOKS}

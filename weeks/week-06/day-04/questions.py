from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DemoQuestion:
    question_ru: str
    expect_ru: str
    source_ids: list[str]
    source_titles: list[str]


DEMO_QUESTIONS: list[DemoQuestion] = [
    DemoQuestion(
        question_ru="Какие дикие плоды преобладали в помёте опоссумов осенью?",
        expect_ru=(
            "На первом месте дикий виноград, на втором — каркас (hackberry); также встречаются "
            "дикая слива и дикая яблоня. Отмечается сезонность (пик — октябрь–ноябрь) и то, "
            "что ловушки лучше всего работали у зарослей дикого винограда."
        ),
        source_ids=["37199"],
        source_titles=["Ecology of the Opossum"],
    ),
    DemoQuestion(
        question_ru=(
            "Какую историю про старого Опоссума и завтрак Короля Медведя "
            "рассказывает Дедушка Лягушка?"
        ),
        expect_ru=(
            "Старый Опоссум, предок дядюшки Билли, спрятал завтрак Короля Медведя, а затем "
            "«помогал» его искать, каждый раз незаметно перепрятывая еду в другое место, "
            "пока голодный медведь не пришёл в ярость."
        ),
        source_ids=["14958"],
        source_titles=['Mother West Wind "Why" Stories'],
    ),
]

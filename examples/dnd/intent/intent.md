# Intent: dnd

Work out the core numbers on a Dungeons and Dragons character sheet, fifth-edition rules.

- The **ability modifier** for an ability score is the score minus ten, halved and rounded down. A score runs from 1 to 30.
- The **proficiency bonus** depends only on character level: it is +2 at levels 1 to 4, and goes up by one every four levels after that, reaching +6 at level 20. A level runs from 1 to 20.
- The **spell save DC** is 8 plus the proficiency bonus plus the spellcasting ability modifier.
- The **attack bonus** is the ability modifier, plus the proficiency bonus when the character is proficient with the weapon, and just the ability modifier when they are not.

Four functions in all: the first two are the building blocks, and the last two are built from them.

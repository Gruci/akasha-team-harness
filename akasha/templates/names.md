# Names

Order: (1) a name that the language, a framework, or an outside API fixes, and a public name that others already
call; (2) the rules of the team ([guides]) and the lint rules that are on; (3) the names of nearby code with the
same responsibility; (4) the rules below. Never rename an existing public name only for style: a rename is its own
change, with each caller. Nearby code counts only where one word is usual. Where the count alone shows no usual word,
use one word for the same work, and let the name show the difference when the work differs (one or many, a cache, a
remote call, a file): the rules below tell how.

## What a name means (the reviewer judges it: R10)
1. A name tells what the code does. Its contract and its side effects agree with the name.
2. One word for one kind of work in the same area. When the work differs (a cache, a remote call, a file), the name
   shows the difference: get, fetch, and load are not the same word.
3. One name, one behavior. A wrapper that does more than the code that it wraps has another name.
4. A name of a true-or-false value starts with is, has, can, or should, and gives only true or false.
5. get gives a value that must be there; find can give nothing. A function that changes its input and one that
   returns a new value have different names (sort, sorted).
6. to converts. create, make, of, and from make a new thing.
7. An abbreviation is one word (HttpUrl, userId). Use the abbreviations that the team already uses. Write an English
   word, not Korean in Latin letters.
8. No type in a name. A one-letter name is only for a short loop.

## How a name is written (the linter of the team enforces it)
- Python: function, variable, module lower_case_with_underscores; class CapWords; constant UPPER_CASE.
- TypeScript, JavaScript: function, variable, property lowerCamelCase; class, type, interface, enum, component
  UpperCamelCase; constant of a module CONSTANT_CASE; no I before an interface.
- Java, Kotlin: package lower case; class UpperCamelCase; method lowerCamelCase; constant UPPER_SNAKE_CASE.
- Go: MixedCaps without underscores; an initialism in one case (URL, ID, userID).
- Swift: type UpperCamelCase, the rest lowerCamelCase.
- C: lower case with underscores; a global name long and clear, a local name short.

## Names that a framework gives
- React: a component UpperCamelCase; a hook use…; a prop that takes an event on… (the DOM fixes onClick). The usual
  name of the function that handles it is handle…; follow the nearby components when they differ.
- Spring Data: a repository method starts with find…By, exists…By, count…By, or delete…By.
- Java: a test class ends with Test. Go: no Get before a getter, and no repeat of the package name (widget.New).
- Swift: a factory method starts with make; a method that changes the value is a verb, and the one that returns a new
  value is its -ed or -ing form.

## The words of a screen
- One thing has one main word on each screen: the label of its definition, when the team registered one. A title, a
  button, and another language can say it in their own form (the aliases of the definition).
- The rules above are for code. The words that people read follow the guides of the team for words ([guides] preview).

Sources: PEP 8 · Google Python, TypeScript, Java, and Go style guides · Kotlin coding conventions · Swift API Design
Guidelines · Linux kernel coding style · NAVER Campus Hackday Java convention · Woowa Tech Course method names ·
Spring Data JPA query keywords · IDEAL (linguistic antipatterns) · Toss Frontend Fundamentals · React: Responding to
Events · TOAST UI convention · typescript-eslint naming-convention · Clean Code (names)

# Structure

These lines tell who owns what, and who can depend on whom. They do not name folders: the guide of the team does.

1. An area owns one coherent business responsibility, with the concepts that belong to it. Other areas use it through
   its entry.
2. In an area, three kinds of code have their own place, in files or in functions: the code that takes a request (an
   entry), the rules of the business (the implementation of a definition), and the code that reads or writes data. An
   entry calls a rule: it does not hold the formula or the query itself. A rule does not import an entry.
3. A rule that computes is pure where it can be: the same arguments give the same result. Time, outside state, input
   and output, and each other side effect come in at a place that the name and the description show.
4. Each authoritative business value or decision has one owner and one contract. A screen can format it, show a
   preview of it, or compute it offline under that contract. Use a shared rule where you can. Do not add another
   formula or decision that can disagree with the contract.
5. To extend code is to serve one more case of the same responsibility, with the same contract and the same side
   effects. An option of that responsibility is fine. Do not put another job into the function as a mode: extract the
   step that both need, or make another entry.
6. When the code to change is long or mixed, make the smallest coherent change that the task needs: a correction in
   place, an extraction, a small entry around the old code, or a replacement of one part. Test the behavior that the
   change touches. Do not add another responsibility to that code. A wider rewrite is not part of a task for a
   feature: it is its own task.

Sources: Clean Architecture (the dependency rule) · Ports and Adapters · Functional core, imperative shell ·
Working Effectively with Legacy Code (sprout method) · Branch by Abstraction · Toss Frontend Fundamentals (cohesion,
coupling) · React: Keeping Components Pure (for line 4 only) · the documents of the framework of the team

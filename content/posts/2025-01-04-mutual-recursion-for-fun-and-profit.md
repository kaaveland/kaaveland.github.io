+++
title = "Constraint propagation: Mutual recursion for fun and profit"
date = "2025-01-04"
modified = "2025-01-04"
tags = ["rust", "advent of code", "algorithms"]
[_build]
list = "never"
render = "always"
+++


In fall 2022, my friend [Jakob](https://github.com/itzjacki/) invited our
team to take part in [Advent of Code](https://adventofcode.com). I'd heard of
this before, and decided to join, using it as an excuse to learn some Rust. I
had a ton of fun, and decided that I wanted to complete all of the puzzles from
both 2022 and earlier years. This has probably been one of my bigger side
projects since. I've learned a ton and produced [a lot of rust
code](https://github.com/kaaveland/advent-of-code-rs).  This later lead to
[eugene](https://kaveland.no/eugene/) being written in Rust. All told, this is
probably around 30-40k lines of Rust code on the hobby-side since 2022, and I'm
still enjoying both Rust and Advent of Code.

## Advent of Code 2018 day 16


A little while ago I wrapped up [2018](https://adventofcode.com/2018) after a
long break, and today I want to write a little bit about an elegant solution for
one of the puzzles, namely
[2018-16](https://adventofcode.com/2018/day/16). There's a lot of text there,
and you don't need to read all the details, the brief problem statement is
this:

We are provided with 16 _instructions_ for some sort of virtual machine. For
each instruction, there's a description of how it behaves. The virtual machine
has 4 _registers_. An instruction runs  with 3 arguments that are either
references to a register, or an _immediate_ value. For example:

``` shell
# instruction reg_a reg_b reg_c
addr 2 3 0
# instruction reg_a immediate_b reg_c
addi 2 14 0
```

This snippet says to run the `addr` _instruction_, which will look up the value
in _registers_ `2` and `3`, add them together and write the result to register
`0`. The second example says to call `addi`, which will look up the value in
register 2 and add the _immediate_ operand 14 to it, writing the result to
register 0.

There's only one problem: We don't have the _opcodes_ of the different
instructions. To figure that out, we are provided with many examples that look
like this:

``` shell
Before: [3, 2, 1, 1]
9 2 1 2
After:  [3, 2, 2, 1]
```

The before and after lines show us the _register_ contents, and the line in the
middle is the _opcode_ of some unknown _instruction_, together with its 3
operands. The puzzle essentially boils down to figure out which _opcode_
goes together with which _instruction_.

### Part 1

Part 1 of the puzzle points us in one possible direction to map the _opcode_
and _instruction_ pairs. It asks us to find out how many of the examples
provided to us that behave like 3 or more of the instructions. This is an
invitation to try to run all instructions across all the samples and verify
whether the registers match the after-state. This isn't very hard to do, let's
write some code. We'll start by defining an `Instruction` enum, and implement
the operations:

``` rust
#[derive(Copy, Clone, Debug, Eq, PartialEq)]
enum Instruction {
    Addr, Addi, Mulr, Muli, Banr, Bani, Borr, Bori,
    Setr, Seti, Gtir, Gtri, Gtrr, Eqir, Eqri, Eqrr,
}

```

There's not a lot of scary syntax here. The `#[derive(..)]` macro
auto-implements some traits for us, namely:

- `Copy` means `Instruction` is a value that doesn't become invalid after having
  been moved / passed to someone else, like given to a function call.
- `Debug` gives us the ability to use `Instruction` in format strings with the
  debug representation, which is great to have for test cases and
  debug-output. It makes things like `println!("{instruction:?}");` work.
- `Eq` and `PartialEq` give us `==` and `!=`, and we need `PartialEq` to get
  `Eq`.

To evaluate an instruction, it needs input registers, and it should calculate
some output. Then, we just need to read the description very carefully to
implement each instruction correctly:

``` rust
fn evaluate(
    instruction: Instruction,
    arg_a: usize,
    arg_b: usize,
    arg_c: usize,
    mut registers: [usize; 4],
) -> [usize; 4] {
    use Instruction::*;
    registers[arg_c] = match instruction {
        Addr => registers[arg_a] + registers[arg_b],
        Addi => registers[arg_a] + arg_b,
        Mulr => registers[arg_a] * registers[arg_b],
        Muli => registers[arg_a] * arg_b,
        Banr => registers[arg_a] & registers[arg_b],
        Bani => registers[arg_a] & arg_b,
        Borr => registers[arg_a] | registers[arg_b],
        Bori => registers[arg_a] | arg_b,
        Setr => registers[arg_a],
        Seti => arg_a,
        Gtir => usize::from(arg_a > registers[arg_b]),
        Gtri => usize::from(registers[arg_a] > arg_b),
        Gtrr => usize::from(registers[arg_a] > registers[arg_b]),
        Eqir => usize::from(arg_a == registers[arg_b]),
        Eqri => usize::from(registers[arg_a] == arg_b),
        Eqrr => usize::from(registers[arg_a] == registers[arg_b]),
    };
    registers
}
}
```

We settled for a `usize` for all integer values from the puzzle. It is an
unsigned integer type used for indexing. We can use it here because there are no
negative values present in the puzzle data, and no instruction can cause a value
to become negative. This makes it convenient to index our `registers: [usize;
4]` array with no casting.

Since `registers` is `Copy`, we are provided with our own copied value from our
caller, and can just mutate it locally and return it, so the `mut` in front of
the parameter name means only local mutability, our changes won't be observable
to whoever holds the original `registers` value. Other than that, we `use
Instruction::*` to make the enum variants available without the `Intruction::`
prefix to make this huge match-block a little easier to look at. In Rust,
`bool`s can't be implicitly converted to integer types, like in a lot of
programming languages descended from C, so we do that manually using
`usize::from`.

Now we just need to parse the examples, and we're ready to do part 1.

The input samples look like this:

``` text
Before: [3, 2, 1, 1]
9 2 1 2
After:  [3, 2, 2, 1]
```

There are 2 blank lines between each one. Since this is Advent of Code, we can
afford to use some cheap tricks to parse the input. For example, we can just run
a regex that identifies all numbers and group them into blocks of 4. This feels
a little dirty, but for Advent of Code, that's okay:

``` rust
#[derive(Copy, Clone, Debug, Eq, PartialEq, Default)]
struct Example {
    before: [usize; 4],
    program: [usize; 4],
    after: [usize; 4],
}

fn parse(s: &str) -> impl Iterator<Item = Example> + '_ {
    let number = Regex::new(r"\d+").unwrap();
    s.split("\n\n").map(move |ex| {
        let mut example = Example::default();
        for (index, matched) in number.find_iter(ex).enumerate() {
            let n: usize = matched.as_str().parse().unwrap();
            let rem = index % 4;
            match index / 4 {
                0 => example.before[rem] = n,
                1 => example.program[rem] = n,
                2 => example.after[rem] = n,
                _ => panic!("Too many numbers in block: {index}, {ex}"),
            }
        }
        example
    })
}
```

The `Example` struct has a new trait derived, `Default`, which gives us the
ability to call `Example::default()` to get an initialized value of the
`Example` struct, with every struct member having its `Default` value. Arrays of
numbers default to 0, which is fine here.

Since the `Iterator` we return is only valid as long as the string we get a
reference to, we have to add an anonymous lifetime to it using `+ '_`. It would
be nice if the compiler could hide this from us, and just take care of it under
the covers.

We need to `.unwrap()` on our regex, because compiling a regex will fail if the
regex syntax is illegal. Since this regex is hardcoded, we know it'll always
fail or always work. This would cause our program to crash if the regex was
invalid, but that's fine, it's not recoverable without fixing the source code
anyway.

We split the input string into blocks separated by double blanks. Then we `map`
over each block. The `|ex|` part is lambda syntax: the `move` in front of it
says that the lambda needs to take ownership of some variables that
are local to `parse`, namely `number` (the regex). Otherwise, `number` would go
out of scope and be deleted, and then it wouldn't be okay for us to use it.

We match every number in each block.  The `.enumerate()` iterator
gives us the `index` of each match we find, and we use that to place the numbers
we `.parse()` directly into the right place in our `Example`, which consists of
3 arrays of 4 numbers each.

Now, it is easy to solve part 1 of the puzzle:

``` rust
use Instruction::*;
const ALL: [Instruction; 16] = [
    Addr, Addi, Mulr, Muli, Banr, Bani, Borr, Bori,
    Setr, Seti, Gtir, Gtri, Gtrr, Eqir, Eqri, Eqrr,
];

fn compatible_instructions(example: &Example) -> usize {
    ALL.into_iter()
        .filter(|instruction| {
            let [_, arg_a, arg_b, arg_c] = example.program;
            let out = evaluate(*instruction, arg_a, arg_b, arg_c, example.before);
            out == example.after
        })
        .count()
}
```
I don't know of any way to get a handle of all of the variants of an `enum`, so
we make an `ALL` array with all the instructions we know of. Then, to test which
instructions that match the behavior observed in an example, we filter the
instructions by whether they return the same output as the example or
not. There's a bit more syntax here; we chose to send the `example` to
`compatible_instructions` by reference, saying we expect `&Example` as input. We
didn't need to do this, since `Example` is `Copy`. `filter` receives a reference
to whatever it is filtering, and since we chose to make `evaluate` take
`Instruction` instead of `&Instruction` for its first parameter, we must use `*`
on it when passing it, which creates a copy (This wouldn't work if `Instruction`
wasn't `Copy`).


``` rust
fn part_1(s: &str) -> usize {
    let (examples, _) = s.split_once("\n\n\n").unwrap();
    parse(examples)
        .filter(|example| compatible_instructions(example) >= 3)
        .count()
}
```

Finally, we parse the first section of the input, the one with the
examples, then count how many examples that behave like at least 3
_instructions_.

### Mutual recursion for fun and profit


Part 2 asks us to map each _instruction_ to its _opcode_, the opcode being the
one provided as the first number in the program in the examples. It then asks us
to run the program we've been provided as the second part of the puzzle
input. By looking at the examples, we can see that the minimum opcode is 0 and
the maximum opcode is 15, so we're looking for a mapping between small integers.

Before we've seen any examples, we must assume that any opcode could refer to
any instruction, so the mapping must initially be from 1 opcode to many possible
instructions. Whenever we see a counter example, we `eliminate` that
_instruction_ from the mapping. If this results in only 1 remaining
_instruction_, we `choose` that instruction to be that _opcode_. `choose` will
`eliminate` that instruction from everywhere else. Or, in Rust:

``` rust
fn eliminate(options: &mut Options, place: usize, instruction: usize) {
    // if we successfully removed this instruction
    if remove(options, place, instruction) {
        // and there's only one possible choice left
        if let Some(choice) = choice_made(options, place) {
            // choose that
            choose(options, place, choice);
        }
    }
}

fn choose(options: &mut Options, place: usize, instruction: usize) {
    for target in 0..options.len() {
        // since place is instruction, it can not be valid anywhere else
        if target != place {
            eliminate(options, target, instruction);
        }
    }
}
```

To do this, we need to encode `Options` somehow. This needs to be a mapping, and
since we're mapping between very small ints, an array should do fine. The value
can be a 16-bit unsigned integer, where each bit refers to an index in the `ALL`
array. Initially, all the bits should be on, because we don't know anything yet:

``` rust
type Options = [u16; 16]; // simply an alias

fn initial_options() -> Options {
    [0xffff; 16]
}

fn is_possible(options: &Options, place: usize, instruction: usize) -> bool {
    // the bit that is index place is on
    options[place] & (1 << instruction) > 0
}
```

We need to be able to remove a candidate `instruction` for a `place`. It is
convenient to let this return a bool telling us whether something was actually
removed or not:

``` rust
fn remove(options: &mut Options, place: usize, instruction: usize) -> bool {
    let removed = is_possible(options, place, instruction);
    options[place] &= !(1 << instruction);
    removed
}
```

We need to be able check if a `place` has only a single candidate:

``` rust
fn choice_made(options: Options, place: usize) -> Option<usize> {
    if options[place].count_ones() == 1 {
        Some(options[place].trailing_zeros() as usize)
    } else {
        None
    }
}
```

And that's it, our definition from earlier works now. Now we can identify all
the _opcodes_ by supplying counter-examples to `eliminate`:

``` rust
fn identify_opcodes(examples: &[Example]) -> [usize; 16] {
    let mut options = initial_options();
    for (i, example) in examples.into_iter().enumerate() {
        let [opcode, arg_a, arg_b, arg_c] = example.program;
        for (place, instruction) in ALL.into_iter().enumerate() {
            let out = evaluate(instruction, arg_a, arg_b, arg_c, example.before);
            if out != example.after {
                eliminate(&mut options, opcode, place);
            }
        }
        // Check if we're done
        if options.iter().all(|possible| possible.count_ones() == 1) {
            println!("Done after {i} of {} examples", examples.len());
            break;
        }
    }
    let mut choices = [0; 16];
    for place in 0..options.len() {
        if let Some(choice) = choice_made(&options, place) {
            choices[place] = choice;
        }
    }
    choices
}
```

On my input data, this prints `Done after 29 of 806 examples`. My input has more
constraints than I need, probably in order to work with methods that don't
resolve all the constraints (perhaps a loop that just removes options that can't
work?).

Solving part 2 requires us to establish the mapping and parse the second section
of the input, which are lines of 4 numbers, which we're to treat as `opcode a b
c` and run the correct instruction on them.

``` rust
fn part_2(s: &str) -> usize {
    let (examples, program) = s.split_once("\n\n\n").unwrap();
    let examples: Vec<_> = parse(examples).collect();
    let mapping = identify_opcodes(&examples);
    let mut registers = [0; 4];
    let mut command = [0; 4];
    let number = Regex::new(r"\d+").unwrap();
    for line in program.lines() {
        for (idx, n) in number.find_iter(line).enumerate() {
            command[idx] = n.as_str().parse().unwrap();
        }
        let [opcode, arg_a, arg_b, arg_c] = command;
        registers = evaluate(ALL[mapping[opcode]], arg_a, arg_b, arg_c, registers);
    }
    registers[0]
}
```

## Constraint propagation


The core of the part 2 solution is the mutually recursive pair of functions I
named `choose/eliminate`. Together, they make up an algorithm I know as
constraint propagation. I've encountered exactly this kind of problem multiple
times in Advent of Code now, I've rediscovered it for at least 3 days:

- [2018-16](https://adventofcode.com/2018/day/16)
- [2020-16](https://adventofcode.com/2020/day/16)
- [2020-21](https://adventofcode.com/2020/day/21)

Though they all look different, I've solved them very similarly, with the main
difference being the representation of the problem - bitmaps, like in this post,
or hashmaps of sets, or matrices. We can use this solution because _choosing_ a
value in some place, _constrains_ the possible values in another place. A lot of
puzzles are like that.

For the most part, I don't do much code reuse between different Advent of Code
puzzles, I feel like rediscovering things I know is good for practice. But after
doing this three times, I wanted to take a stab at making a generic version of
it, and use it make a sudoku-solver. Sudoku is a bit different from the puzzles
we've looked at so far. Instead of being able to eliminate _everywhere_ other
than where we're choosing, we have to have some notion of _neighbours_ (to
return the 3x3 grid we're in, our row, and our column). That'll still work with
the puzzle from earlier though, we'll just say that everyone's a neighbour in
that one.


So, let's try to implement something a little more generic:

``` rust
trait Possibilities<K: Copy, V: Copy> {
    fn set(&mut self, place: K, value: V);
    fn remove(&mut self, place: K, value: V) -> bool;
    fn choice_made(&self, place: K) -> Option<V>;
    fn neighbours(&self, place: K) -> impl Iterator<Item = K>;

    fn eliminate(&mut self, place: K, value: V) {
        if self.remove(place, value) {
            if let Some(choice) = self.choice_made(place) {
                self.choose(place, choice);
            }
        }
    }
    fn choose(&mut self, place: K, value: V) {
        self.set(place, value);
        for target in self.neighbours(place).collect::<Vec<_>>() {
            self.eliminate(target, value);
        }
    }
}

```

This introduces a trait of 4 methods that must be provided, and 2 that are
automatically provided. There's a bit more syntax here. To provide an
implementation of this trait, you must specify a `K` and a `V` type, that both
implement `Copy`. `K` is like an index, or coordinate, and `V` is like a value
that is a valid choice, like an `Instruction` or an index into the `ALL` array
from earlier.

Implementing it for a bitmap-based array, like the one from earlier could look
like this:

``` rust
impl<const N: usize> Possibilities<usize, usize> for [u16; N] {
    fn set(&mut self, place: usize, value: usize) {
        self[place] = 1 << value;
    }

    fn remove(&mut self, place: usize, value: usize) -> bool {
        let bit = 1 << value;
        let set = self[place] & bit;
        self[place] &= !bit;
        set > 0
    }

    fn choice_made(&self, place: usize) -> Option<usize> {
        if self[place].count_ones() == 1 {
            Some(self[place].trailing_zeros() as usize)
        } else {
            None
        }
    }

    fn neighbours(&self, place: usize) -> impl Iterator<Item = usize> {
        (0..N).filter(move |n| *n != place)
    }
}
```

This uses `const N: usize` as a generic to enable it to work for arrays of any
length. Note that since it's still using `u16`, it doesn't really make sense to
use a higher value for `N` than 16 here. The change to `identify_opcodes` is
very minor, we now call `options.eliminate()` instead of `eliminate(&mut options,
...)` and `options.choice_made()` instead of `choice_made(&options)`, but other
than that, it works the same as what we had earlier.

## Solving sudoku

We have what we need in order to solve sudoko now, so let's start pondering how
to represent the board, and the possibilities. Each cell in sudoko can contain 9
possible numbers, so with the bitmask approach, that fits within 16 bits. There
are 81 squares, and it might be convenient to index them with a pair of
coordinates, but we can still represent it as a flat array in memory and just
translate the lookups. Since there are only 9 possible numbers, we can use
`u8` as our value type.

We'll make a simple wrapper around the array, so we can name types more easily:

``` rust
#[derive(Debug, Eq, PartialEq)]
struct SudokoOptions {
    options: [u16; 81],
}

impl Default for SudokoOptions {
    fn default() -> Self {
        // avoiding the zeroth bit will make it easier for us to make output later
        let everything_possible = ((1 << 10) - 1) ^ 1;
        SudokoOptions {
            options: [everything_possible; 81],
        }
    }
}
```

We'll use x, y coordinates to index into `options`. We know the width of the
board to be 9, so `x + y * 9` should give us the right spot. The `remove` and
`choice_made` functions are similar to before, but `neighbours` is more
involved. We floor-divide the `x` and `y` coordinates by 3, to truncate them
to `[0, 2]`. Then we multiply that by 3 so get the first `x, y` coordinate of
the "square" that contains `(x, y)`. We iterate over the 9 cells in the square
by using division and modulo by 3 to separate into `x` and `y`.


``` rust
impl Possibilities<(usize, usize), usize> for SudokoOptions {
    fn remove(&mut self, place: (usize, usize), value: usize) -> bool {
        let ix = place.0 + place.1 * 9;
        let bit = 1 << value;
        let set = self.options[ix] & bit;
        self.options[ix] &= !bit;
        set > 0
    }

    fn choice_made(&self, place: (usize, usize)) -> Option<usize> {
        let ix = place.0 + place.1 * 9;
        if self.options[ix].count_ones() == 1 {
            Some(self.options[ix].trailing_zeros() as usize)
        } else {
            None
        }
    }

    fn neighbours(&self, place: (usize, usize))
      -> impl Iterator<Item = (usize, usize)> {
        let (x, y) = place;
        let row = (0..9).map(move |x| (x, y));
        let col = (0..9).map(move |y| (x, y));
        let (xstart, ystart) = (3 * (x / 3), 3 * (y / 3));
        let square = (0..9).map(move |s| (xstart + s / 3, ystart + s % 3));
        row.chain(col)
            .chain(square)
            .filter(move |neighbour| *neighbour != place)
    }
}
```

We'll need to call `.choose()` for each number we're provided to solve the
puzzle. If the puzzle has more than 1 possible solution, that won't be enough,
but we can think about that later. Let's arbitrarily decide that our input is
strings of 9 lines, where each line consists of 9 characters. The characters
are either `'.'`, to say that the character is unknown, or it is a
number. Then, this should give us the solution for fully specified puzzles:

``` rust
fn sudoko(puzzle: &str) -> SudokoOptions {
    let mut board = SudokoOptions::default();
    let known = puzzle.lines().enumerate().flat_map(|(y, line)| {
        line.as_bytes()
            .iter()
            .enumerate()
            .filter_map(move |(x, ch)| {
                if *ch != b'.' {
                    Some(((x, y), *ch - b'0'))
                } else {
                    None
                }
            })
    });
    for (place, value) in known {
        board.choose(place, value);
    }
    board
}
```

To test it, we'll use the easy puzzle from
[wikipedia](https://en.wikipedia.org/wiki/Sudoku#/media/File:Sudoku_Puzzle_by_L2G-20050714_standardized_layout.svg):

``` rust
const EASY_PUZZLE: &str = "53..7....
6..195...
.98....6.
8...6...3
4..8.3..1
7...2...6
.6....28.
...419..5
....8..79"
```

To compare, it would be nice to be able to make a string from a solved
`SudokoOptions`, so let's do that as well:

``` rust
impl SudokoOptions {
    fn try_to_string(&self) -> Result<String, String> {
        let mut out = String::new();
        for y in 0..9 {
            for x in 0..9 {
                if let Some(choice) = self.choice_made((x, y)) {
                    out.push((choice + b'0') as char);
                } else {
                    return Err(format!("{x}, {y} unresolved"));
                }
            }
            out.push('\n');
        }
        Ok(out)
    }
}
```

And sure enough, running `sudoko(EASY_PUZZLE)` yields the answer:

``` shell
➜  sudoku git:(main) pbpaste| target/release/sudoku
534678912
672195348
198342567
859761423
426853791
713924856
961537284
287419635
345286179
```

In fact, this problem is over-constrained, and we don't need every input value
we're provided with to solve it, exactly like with the
instruction/opcode-mapping from earlier. For example, we can remove the 9 from
the last cell, and the 9 next to 41 near the bottom, and it'll still work. If,
on the other hand, the problem is under-constrained, we'll need to try to apply
some choices and just see if they work out, and currently the design we made
won't support that. We will need to modify it so that `choose` tells us whether
the puzzle is still possible to solve, by identifying that a contradiction has
happened, or whether all possible choices for some `K` have disappeared. I might
do a followup on that later.

There's a bit of additional code that was required for making it take input from
stdin, which is available in a little
[repository](https://github.com/kaaveland/sudoko-rs/tree/main) I made from the
code in this blogpost. The repository has code to solve Advent of Code 2018/16,
as well as a sudoku-solver. Most of the code from this blogpost is there,
although small refactorings were done to use the `Possibilities` trait instead
of the functions working directly on `[u16; 16]`.

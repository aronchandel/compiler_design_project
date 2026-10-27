# Arrays, Pointers, and `<climits>` Extension Documentation

This document describes the design, semantics, internal representations, and operational boundaries of the C++ array, pointer, and `<climits>` extensions added to `cpp2py`.

---

## 1. `<climits>` Header and Macro Resolution

### Supported Constructs
- Recognition of preprocessor include: `#include <climits>` (in conjunction with or separate from `#include <iostream>`).
- All 16 standard C++ integer-limit macros:
  - `CHAR_BIT`
  - `SCHAR_MIN`, `SCHAR_MAX`, `UCHAR_MAX`
  - `SHRT_MIN`, `SHRT_MAX`, `USHRT_MAX`
  - `INT_MIN`, `INT_MAX`, `UINT_MAX`
  - `LONG_MIN`, `LONG_MAX`, `ULONG_MAX`
  - `LLONG_MIN`, `LLONG_MAX`, `ULLONG_MAX`

### Value Determination & Portability
- Values are **not** hardcoded to fixed assumptions. Instead, they are dynamically bound to the configured `TargetModel` in `cpp2py/config.py`.
- `TargetModel` parameterizes `char_bits` (8), `short_bits` (16), `int_bits` (32), `long_bits` (auto-detected: 32 on Windows/MinGW, 64 on LP64 platforms), and `long_long_bits` (64).
- During semantic analysis, when `#include <climits>` is present, macros are resolved into constants. In the lowered IR and generated Python code, macros appear as resolved numeric constants. Unresolved C++ macro names never leak into generated Python code.
- If `#include <climits>` is omitted and a macro is used, semantic analysis emits standard diagnostic `E3001` (undeclared identifier).

---

## 2. C++ Arrays

### Supported Subset
- **Declaration with constant size:** `int arr[N];`
- **Initializers:** `int arr[3] = {10, 20, 30};`
- **Partial initialization:** `int arr[4] = {1, 2};` (remaining elements are zero-initialized per C++ standard).
- **Default initialization:** `int arr[N];` initializes elements to `0`.
- **Element access & modification:** `arr[i] = val;` and reading `arr[i]` in expressions.
- **Compound assignments & inc/dec:** `arr[i] += 5;`, `arr[i]++;`, `--arr[i];`
- **Standard loops:** Array traversal in `for` and `while` loops.
- **Function parameters:** Functions accepting arrays (e.g. `void f(int arr[], int n)` or `void f(int *arr, int n)`). Mutations inside the function modify the caller's array elements in-place.
- **Stream I/O:** Reading into array elements via `cin >> arr[i];` and printing via `cout << arr[i];`.

### Deliberately Unsupported & Diagnostics
- **Multidimensional arrays:** `int matrix[3][3];` is rejected with diagnostic `E4001` (`multidimensional arrays are unsupported`).
- **Dynamic or variable-length arrays:** Array sizes must be constant integer expressions; negative or non-constant sizes produce `E3003`.
- **Excess initializers:** Providing more initializers than declared array capacity produces `E3003`.

---

## 3. C++ Pointers and Memory Aliasing

### Supported Subset
- **Pointer declarations:** `int *p;` and `int *p = &x;`
- **Address-of operator:** `&x` on scalar variables and `&arr[i]` on array elements.
- **Dereference operator:** `*p` for both reading and writing (`*p = val;`). Writing through `*p` directly mutates the referenced variable `x`.
- **Pointer aliasing:** `int *p1 = &x; int *p2 = p1; *p2 = 50;` preserves aliasing so that `*p1 == 50` and `x == 50`.
- **Null pointers:** `nullptr` literal, assignment `int *p = nullptr;`, comparison `p == nullptr`, `p != nullptr`, and boolean tests `if (!p)`.
- **Function parameters:** Pointer parameters (e.g. `void modify(int *p)`). Passing `&x` allows the callee to mutate `x`.
- **Pointer arithmetic:**
  - Addition of pointer and integer: `p + i` and `i + p`
  - Subtraction of integer from pointer: `p - i`
  - Pointer increment/decrement: `p++`, `++p`, `p--`, `--p`
  - Pointer difference: `p2 - p1` produces the integer distance (number of elements) between two pointers into the same array.
- **Array-to-pointer decay:** Assigning an array or passing an array to a pointer parameter automatically decays into a pointer to the array's first element (`_Ptr(arr, 0)`).
- **Stream I/O:** Reading into dereferenced pointers via `cin >> *p;`.

### Memory & Aliasing Representation
- **Scalar Variable Boxing:**
  - Ordinary scalar variables whose address is never taken remain plain, native Python variables (`x = 42`) with **zero runtime overhead**.
  - Scalar variables whose address is taken (`&x`) are identified by semantic analysis (`addressed_symbols`) and lowered as 1-element Python lists (`x = [42]`). Direct reads/writes to `x` access `x[0]`.
- **`_Ptr` Helper Class:**
  - Pointers are represented by the compatibility helper `_Ptr(target, offset)`.
  - For scalar `&x`, the pointer is `_Ptr(x, 0)`.
  - For array `arr`, pointer is `_Ptr(arr, 0)` or `_Ptr(arr, offset)`.
  - Dereferencing `*p` maps to `p[0]`, accessing `target[offset]`.
  - Dereferencing `nullptr` (`_Ptr(None, 0)`) raises `RuntimeError("Segmentation fault: dereferencing nullptr")`.
  - Pointer addition/subtraction creates a new `_Ptr` referencing the same underlying list with an adjusted offset.

---

## 4. Semantic Compatibility Integration
- Pointer and array operations preserve standard integer promotion and overflow compatibility rules established in Phase 5.
- Pointer arithmetic operates on element indices rather than raw byte offsets, matching C++ pointer stride semantics.
- Pointer difference across distinct target objects raises a runtime error, matching C++ undefined behaviour boundaries.

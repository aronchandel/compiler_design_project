#include <iostream>
using namespace std;

int collatz(int n) {
    int steps = 0;
    while (n != 1) {
        if (n % 2 == 0) {
            n /= 2;
        } else {
            n = 3 * n + 1;
        }
        steps++;
    }
    return steps;
}

int main() {
    int n;
    cin >> n;
    cout << collatz(n) << endl;
    return 0;
}

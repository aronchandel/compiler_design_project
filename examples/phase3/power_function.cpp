#include <iostream>
using namespace std;

int power(int base, int exp) {
    int res = 1;
    for (int i = 0; i < exp; i++) {
        res *= base;
    }
    return res;
}

int main() {
    cout << power(2, 8) << endl;
    return 0;
}

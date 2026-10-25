#include <iostream>
using namespace std;

int main() {
    int total = 0;
    for (int i = 1; i <= 5; ++i) {
        int neg = -i;
        int q = neg / 2;
        int r = neg % 2;
        total = total + q + r;
    }
    cout << total << endl;
    return 0;
}

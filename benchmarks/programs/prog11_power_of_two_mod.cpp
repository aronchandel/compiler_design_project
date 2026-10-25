#include <iostream>
using namespace std;

int main() {
    int sum = 0;
    for (int i = 1; i <= 16; ++i) {
        int r = i % 4;
        sum = sum + r;
    }
    cout << sum << endl;
    return 0;
}

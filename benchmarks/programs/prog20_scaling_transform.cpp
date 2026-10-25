#include <iostream>
using namespace std;

int main() {
    int total = 0;
    for (int i = 0; i < 10; ++i) {
        int scaled = (i * 5) / 10;
        int rem = (i * 5) % 10;
        total = total + scaled + rem;
    }
    cout << total << endl;
    return 0;
}

#include <iostream>
using namespace std;

int sign(int x) {
    if (x > 0) {
        return 1;
    }
    if (x < 0) {
        return -1;
    }
    return 0;
}

int main() {
    cout << sign(5) << endl;
    cout << sign(-12) << endl;
    cout << sign(0) << endl;
    return 0;
}

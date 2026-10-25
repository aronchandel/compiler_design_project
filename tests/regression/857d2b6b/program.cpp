#include <iostream>
using namespace std;

int main() {
    int a = 2, b = 1;
    cin >> a >> b;
    if (a >= b) {
        a = b;
    } else {
        a = (b - a);
    }
    if (b > b) {
        b = a;
    } else {
        b = (42 + b);
    }
    cout << a << endl;
    cout << b << endl;
    return 0;
}

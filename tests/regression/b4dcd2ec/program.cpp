#include <iostream>
using namespace std;

int main() {
    int a = -1, b = 5, c = -1, x = 5, y = 10;
    cin >> a;
    c = ((y - a) * a);
    for (int iter_1 = 0; iter_1 < 4; iter_1 = iter_1 + 1) {
        y = y + -1;
    }
    if (a <= y) {
        y = 1;
    } else {
        y = (a * 1);
    }
    for (int iter_3 = 0; iter_3 < 5; iter_3 = iter_3 + 1) {
        b = b + -1;
    }
    cout << a << endl;
    cout << b << endl;
    cout << c << endl;
    cout << x << endl;
    cout << y << endl;
    return 0;
}

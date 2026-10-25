#include <iostream>
using namespace std;

int main() {
    int a = 5, b = 1, c = 2, x = 2, y = 5;
    cin >> a >> b;
    for (int iter_0 = 0; iter_0 < 3; iter_0 = iter_0 + 1) {
        a = a + 3;
    }
    for (int iter_1 = 0; iter_1 < 4; iter_1 = iter_1 + 1) {
        b = b + -2;
    }
    c = b;
    b = ((100 * x) * (3 - c));
    cout << a << endl;
    cout << b << endl;
    cout << c << endl;
    cout << x << endl;
    cout << y << endl;
    return 0;
}

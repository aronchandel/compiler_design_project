#include <iostream>
using namespace std;

int main() {
    int a = -1, b = 2, c = 1;
    cin >> a;
    c = (b - (c / (-3)));
    for (int iter_1 = 0; iter_1 < 2; iter_1 = iter_1 + 1) {
        b = b + -1;
    }
    for (int iter_2 = 0; iter_2 < 5; iter_2 = iter_2 + 1) {
        a = a + -2;
    }
    b = a;
    cout << a << endl;
    cout << b << endl;
    cout << c << endl;
    return 0;
}

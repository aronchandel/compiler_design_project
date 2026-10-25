#include <iostream>
using namespace std;

int main() {
    int a = 10, b = 10, c = 10, x = 5;
    cin >> a >> b;
    b = b;
    for (int iter_1 = 0; iter_1 < 2; iter_1 = iter_1 + 1) {
        b = b + 1;
    }
    cout << a << endl;
    cout << b << endl;
    cout << c << endl;
    cout << x << endl;
    return 0;
}

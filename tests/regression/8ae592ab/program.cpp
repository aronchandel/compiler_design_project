#include <iostream>
using namespace std;

int main() {
    int a = 2, b = -1;
    cin >> a;
    if (b <= a) {
        a = a;
    } else {
        a = 1;
    }
    for (int iter_1 = 0; iter_1 < 2; iter_1 = iter_1 + 1) {
        a = a + 2;
    }
    for (int iter_2 = 0; iter_2 < 2; iter_2 = iter_2 + 1) {
        a = a + 1;
    }
    cout << a << endl;
    cout << b << endl;
    return 0;
}

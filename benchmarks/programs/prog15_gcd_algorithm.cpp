#include <iostream>
using namespace std;

int main() {
    int a = 48;
    int b = 18;
    while (b > 0) {
        int t = a % b;
        a = b;
        b = t;
    }
    cout << a << endl;
    return 0;
}

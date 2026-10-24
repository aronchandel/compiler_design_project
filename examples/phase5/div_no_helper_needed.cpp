#include <iostream>
using namespace std;

int main() {
    int i = 0;
    while (i < 10) {
        int d = i / 2;
        int m = i % 2;
        cout << d << " " << m << endl;
        i += 1;
    }
    return 0;
}

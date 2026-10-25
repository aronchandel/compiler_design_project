#include <iostream>
using namespace std;

int main() {
    int acc = 0;
    for (int i = 0; i < 5; ++i) {
        for (int j = 1; j <= 5; ++j) {
            int term = (i * 10) / j;
            acc = acc + term;
        }
    }
    cout << acc << endl;
    return 0;
}

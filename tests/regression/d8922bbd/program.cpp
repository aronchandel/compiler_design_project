#include <iostream>
using namespace std;
int main() {
    int sum = 0;
    for (int i = -5; i < 0; i = i + 1) {
        sum = sum + (i % 2);
    }
    cout << sum << endl;
    return 0;
}

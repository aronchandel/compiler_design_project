#include <iostream>
using namespace std;

int main() {
    int x;
    cin >> x;
    if (x > 0) {
        cout << "positive" << endl;
    } else if (x < 0) {
        cout << "negative" << endl;
    } else {
        cout << "zero" << endl;
    }
    return 0;
}

#include <iostream>
using namespace std;
int main() {
    int n;
    cin >> n;
    int sum = 0;
    for (int i = 0; i < n; i = i + 1) {
        int v;
        cin >> v;
        sum = sum + v;
    }
    cout << sum << endl;
    return 0;
}
